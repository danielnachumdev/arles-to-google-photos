"""Publish a preview job to Google Photos as a new independent upload job."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from ..export.preview import AlbumPreview
from ..progress import JobCancelled
from .cancel import cancellable_sink, store_is_cancelled
from .events import JobEventBus
from .store import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    TYPE_UPLOAD,
    JobNotFoundError,
)


class _JobLike(Protocol):
    id: str
    root: Path
    status: str
    type: str
    preview: Optional[AlbumPreview]


class _StoreLike(Protocol):
    def get(self, job_id: str) -> _JobLike:
        ...

    def ensure_local_root(self, job_id: str) -> Path:
        ...

    def ensure_artifact_file(self, job_id: str, relpath: str) -> Path:
        ...

    def create_upload_from(
        self,
        source_id: str,
        *,
        parent_job_id: Optional[str] = None,
    ) -> _JobLike:
        ...

    def set_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None,
        *,
        job_type: Optional[str] = None,
    ) -> Any:
        ...

    def mark_done(self, job_id: str, product_url: str) -> Any:
        ...

    def retains_full_local_tree(self) -> bool:
        ...


class _PublisherLike(Protocol):
    def publish(
        self,
        gp: Any,
        root: Path,
        preview: AlbumPreview,
        sink: Any = None,
        *,
        resolve: Any = None,
        release: Any = None,
    ) -> Any:
        ...


class PublishService:
    """Create a new upload job, run AlbumPublisher, and emit SSE on that job."""

    def __init__(
        self,
        store: _StoreLike,
        publisher: _PublisherLike,
        events: JobEventBus,
        gp_factory: Callable[[str], Any],
        submit: Optional[Callable[[str, Callable[[], None]], None]] = None,
    ) -> None:
        self._store = store
        self._publisher = publisher
        self._events = events
        self._gp_factory = gp_factory
        self._submit = submit

    def publish(self, job_id: str, *, access_token: str) -> str:
        upload_id = self.start(job_id, access_token=access_token)
        self.finish(upload_id, access_token=access_token)
        return upload_id

    def launch(
        self,
        source_id: str,
        *,
        access_token: str,
        parent_job_id: Optional[str] = None,
    ) -> str:
        """Start upload as pending and enqueue finish. Returns the upload id."""
        upload_id = self.start(
            source_id, access_token=access_token, parent_job_id=parent_job_id
        )
        token = access_token
        if self._submit is not None:
            self._submit(
                upload_id, lambda: self._finish_safe(upload_id, token)
            )
        else:
            self._finish_safe(upload_id, token)
        return upload_id

    def start(
        self,
        source_id: str,
        *,
        access_token: str,
        parent_job_id: Optional[str] = None,
    ) -> str:
        try:
            job = self._store.get(source_id)
        except JobNotFoundError:
            raise
        if job.preview is None:
            raise ValueError("preview not ready")
        if job.type == TYPE_UPLOAD and job.status == STATUS_RUNNING:
            raise ValueError("publish already in progress")
        if not job.preview.items:
            raise ValueError("no items to publish")

        token = (access_token or "").strip()
        if not token:
            raise ValueError("google access token required")

        if parent_job_id:
            upload = self._store.create_upload_from(
                source_id, parent_job_id=parent_job_id
            )
        else:
            upload = self._store.create_upload_from(source_id)
        total = len(upload.preview.items) if upload.preview is not None else 0
        self._events.emit(
            upload.id,
            "publish",
            "Starting upload",
            current=0,
            total=total,
        )
        if parent_job_id:
            self._events.emit(
                parent_job_id,
                "child",
                upload.id,
                extra={"child_id": upload.id, "type": TYPE_UPLOAD},
            )
        return upload.id

    def _finish_safe(self, upload_id: str, access_token: str) -> None:
        try:
            self.finish(upload_id, access_token=access_token)
        except Exception:
            return

    def finish(self, upload_id: str, *, access_token: str) -> str:
        job = self._store.get(upload_id)
        if job.preview is None:
            raise ValueError("preview not ready")
        if not job.preview.items:
            raise ValueError("no items to publish")
        if job.status == STATUS_PENDING:
            self._store.set_status(upload_id, STATUS_RUNNING, job_type=TYPE_UPLOAD)

        total = len(job.preview.items)
        try:
            if store_is_cancelled(self._store, upload_id):
                raise JobCancelled()
            gp = self._gp_factory((access_token or "").strip())
            album_root = self._store.ensure_local_root(upload_id)

            def resolve(relpath: str) -> Path:
                return self._store.ensure_artifact_file(upload_id, relpath)

            release = None
            if not self._store.retains_full_local_tree():

                def release(relpath: str) -> None:
                    path = album_root / relpath
                    if not path.is_file():
                        return
                    try:
                        path.unlink()
                        path.write_bytes(b"")
                    except OSError:
                        pass

            album = self._publisher.publish(
                gp,
                album_root,
                job.preview,
                sink=cancellable_sink(
                    self._events.sink_for(upload_id), self._store, upload_id
                ),
                resolve=resolve,
                release=release,
            )
            if store_is_cancelled(self._store, upload_id):
                raise JobCancelled()
            url = getattr(album, "productUrl", "") or ""
            self._store.mark_done(upload_id, url)
            self._events.emit(
                upload_id,
                "done",
                url,
                current=total,
                total=total,
                extra={"product_url": url},
            )
            return url
        except JobCancelled:
            self._mark_cancelled(upload_id)
            return ""
        except Exception as exc:
            if store_is_cancelled(self._store, upload_id):
                self._mark_cancelled(upload_id)
                return ""
            message = _format_publish_failure(exc)
            self._store.set_status(
                upload_id, STATUS_FAILED, error=message, job_type=TYPE_UPLOAD
            )
            self._events.emit(upload_id, "error", message)
            raise

    def _mark_cancelled(self, upload_id: str) -> None:
        job = self._store.get(upload_id)
        if getattr(job, "status", None) == STATUS_CANCELLED:
            return
        self._store.set_status(upload_id, STATUS_CANCELLED, job_type=TYPE_UPLOAD)
        self._events.emit(upload_id, "cancelled", "Job cancelled")


def _format_publish_failure(exc: BaseException) -> str:
    """Human-readable publish failure for job.error / SSE (not a bare path)."""
    text = str(exc).strip() or type(exc).__name__
    lowered = text.lower()
    if lowered.startswith("google photos rejected") or lowered.startswith(
        "could not load photo"
    ) or lowered.startswith("could not prepare"):
        return text
    if isinstance(exc, FileNotFoundError):
        return (
            f"Could not load a photo for Google Photos upload ({text}). "
            "The file is missing from server storage."
        )
    # requests.HTTPError subclasses OSError — do not call that a local read error.
    try:
        from requests import HTTPError, RequestException
    except ImportError:
        HTTPError = ()  # type: ignore[misc, assignment]
        RequestException = ()  # type: ignore[misc, assignment]
    if isinstance(exc, (HTTPError, RequestException)) or "photoslibrary.googleapis.com" in text:
        return f"Google Photos API error during upload: {text}"
    if isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError):
        errno = getattr(exc, "errno", None)
        # Local filesystem / errno-based failures only.
        if errno is not None or getattr(exc, "filename", None):
            return f"Could not read a photo for Google Photos upload: {text}"
    return text
