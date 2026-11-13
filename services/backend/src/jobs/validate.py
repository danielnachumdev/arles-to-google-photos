"""Manual validate job: remote Arles tree vs app-created Google Photos albums."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Protocol
from urllib.parse import urlparse

from ..export.validate import (
    PhotosAlbumIndexer,
    RemoteAlbumDiscovery,
    compare_indexes,
)
from ..progress import JobCancelled, ProgressSink
from .cancel import cancellable_sink, store_is_cancelled
from .persistence.state import ORIGIN_WEB
from .scraper import validate_scrape_url
from .store import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
    TYPE_VALIDATE,
    JobNotFoundError,
)
from .tokens import AccessTokenVault


class _StoreLike(Protocol):
    def create(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def get(self, job_id: str) -> Any:
        ...

    def set_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None,
        *,
        job_type: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> Any:
        ...

    def update_extra(self, job_id: str, extra: Optional[Dict[str, Any]]) -> Any:
        ...

    def mark_done(self, job_id: str, product_url: str = "") -> Any:
        ...


class _EventsLike(Protocol):
    def emit(
        self,
        job_id: str,
        stage: str,
        message: str = "",
        *,
        current: int = 0,
        total: int = 0,
        extra: Optional[Dict[str, Any]] = None,
        kind: str = "",
        audience: str = "",
    ) -> Any:
        ...


class ValidateService:
    """Create TYPE_VALIDATE jobs; discover remote + index Photos; persist report."""

    def __init__(
        self,
        store: _StoreLike,
        events: _EventsLike,
        gp_factory: Callable[[str], Any],
        *,
        jobs_root: Path,
        vault: Optional[AccessTokenVault] = None,
        discovery: Optional[RemoteAlbumDiscovery] = None,
        photos_indexer: Optional[PhotosAlbumIndexer] = None,
        submit: Optional[Callable[[str, Callable[[], None]], None]] = None,
    ) -> None:
        self._store = store
        self._events = events
        self._gp_factory = gp_factory
        self._jobs_root = Path(jobs_root)
        self._vault = vault or AccessTokenVault()
        self._discovery = discovery or RemoteAlbumDiscovery()
        self._photos = photos_indexer or PhotosAlbumIndexer()
        self._submit = submit

    def start(
        self,
        url: str,
        *,
        access_token: str,
        headers: Optional[Mapping[str, str]] = None,
        owner_id: Optional[str] = None,
    ) -> str:
        token = (access_token or "").strip()
        if not token:
            raise ValueError("google access token required")
        scrape_url = validate_scrape_url(url)
        header_map: Optional[Dict[str, str]] = None
        if headers:
            header_map = {str(key): str(value) for key, value in headers.items()}
        folder_label = urlparse(scrape_url).netloc or None
        job = self._store.create(
            self._jobs_root,
            job_type=TYPE_VALIDATE,
            folder_label=folder_label,
            scrape_url=scrape_url,
            scrape_headers=header_map,
            import_origin=ORIGIN_WEB,
            owner_id=owner_id,
        )
        self._vault.put(job.id, token)
        self._events.emit(job.id, "validate", "Starting validation")
        return job.id

    def finish(self, job_id: str, *, access_token: Optional[str] = None) -> None:
        token = (access_token or "").strip() or (self._vault.pop(job_id) or "")
        if not token:
            self._fail(job_id, "google access token required", error_code="auth")
            return
        job = self._store.get(job_id)
        if job.status != STATUS_RUNNING:
            self._store.set_status(job_id, STATUS_RUNNING, job_type=TYPE_VALIDATE)
        scrape_url = job.scrape_url
        headers = dict(job.scrape_headers or {})
        try:
            if store_is_cancelled(self._store, job_id):
                raise JobCancelled()
            if not scrape_url:
                raise ValueError("validate url missing")
            sink = self._sink(job_id)
            self._events.emit(job_id, "discover", "Discovering remote albums")
            remote, remote_warnings = self._discovery.discover(
                scrape_url, headers=headers, sink=sink
            )
            if store_is_cancelled(self._store, job_id):
                raise JobCancelled()
            self._events.emit(job_id, "photos", "Indexing Google Photos albums")
            gp = self._gp_factory(token)
            photos, photos_warnings = self._photos.index(gp, sink=sink)
            if store_is_cancelled(self._store, job_id):
                raise JobCancelled()
            report = compare_indexes(
                root_url=scrape_url,
                remote=remote,
                photos=photos,
                warnings=[*remote_warnings, *photos_warnings],
            )
            self._store.update_extra(
                job_id, {"validation_report": report.to_dict()}
            )
            self._store.set_status(job_id, STATUS_DONE, job_type=TYPE_VALIDATE)
            self._events.emit(
                job_id,
                "done",
                "Validation complete",
                extra={
                    "identical": report.identical,
                    "summary": report.summary,
                },
            )
        except JobCancelled:
            self._vault.discard(job_id)
            if not store_is_cancelled(self._store, job_id):
                self._store.set_status(
                    job_id, STATUS_CANCELLED, job_type=TYPE_VALIDATE
                )
            self._events.emit(job_id, "cancelled", "Validation cancelled")
        except Exception as exc:  # noqa: BLE001
            self._vault.discard(job_id)
            if store_is_cancelled(self._store, job_id):
                self._events.emit(job_id, "cancelled", "Validation cancelled")
                return
            self._fail(job_id, str(exc) or exc.__class__.__name__)

    def launch(
        self,
        url: str,
        *,
        access_token: str,
        headers: Optional[Mapping[str, str]] = None,
        owner_id: Optional[str] = None,
    ) -> str:
        job_id = self.start(
            url,
            access_token=access_token,
            headers=headers,
            owner_id=owner_id,
        )
        token = access_token

        def _run() -> None:
            self.finish(job_id, access_token=token)

        if self._submit is not None:
            self._submit(job_id, _run)
        else:
            _run()
        return job_id

    def _sink(self, job_id: str) -> ProgressSink:
        return cancellable_sink(
            self._events.sink_for(job_id), self._store, job_id
        )

    def _fail(
        self,
        job_id: str,
        message: str,
        *,
        error_code: Optional[str] = None,
    ) -> None:
        try:
            self._store.set_status(
                job_id,
                STATUS_FAILED,
                error=message,
                job_type=TYPE_VALIDATE,
                error_code=error_code,
            )
        except JobNotFoundError:
            return
        self._events.emit(job_id, "error", message)
