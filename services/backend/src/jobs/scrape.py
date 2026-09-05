"""Run a scrape job off the event loop: download → artifacts → child jobs."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Set
from urllib.parse import urlparse

from ..export.scrape.scraper import (
    NotArlesGalleryError,
    ScrapeEmptyError,
    ScrapeFetchError,
)
from ..progress import FanOutProgressSink, JobCancelled
from .cancel import cancellable_sink, store_is_cancelled
from .persistence.state import ORIGIN_WEB
from .scraper import (
    AlbumScraper,
    normalize_scrape_result,
    should_spawn_preview_child,
    validate_scrape_url,
)

ERROR_NOT_ARLES = "not_arles"
ERROR_FETCH_FAILED = "fetch_failed"
ERROR_SCRAPE_EMPTY = "scrape_empty"
_CLASSIFIED_SCRAPE_CODES = frozenset(
    {ERROR_NOT_ARLES, ERROR_FETCH_FAILED, ERROR_SCRAPE_EMPTY}
)
from .store import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_WAITING,
    TYPE_PREVIEW,
    TYPE_SCRAPE,
    Job,
    JobStore,
)


class _WorkspaceLike(Protocol):
    def materialize(self, files: Any) -> Path:
        ...


class _ParserLike(Protocol):
    def parse(self, root: Path, sink: Any = None) -> Any:
        ...


class _EventBusLike(Protocol):
    def emit(
        self,
        job_id: str,
        stage: str,
        message: str = "",
        *,
        current: int = 0,
        total: int = 0,
        extra: Optional[Any] = None,
        kind: Optional[str] = None,
        audience: Optional[str] = None,
    ) -> None:
        ...

    def sink_for(self, job_id: str) -> Any:
        ...


class _AutoPublisherLike(Protocol):
    def remember(self, job_id: str, token: str) -> None:
        ...

    def discard(self, job_id: str) -> None:
        ...

    def after_preview(
        self,
        preview_id: str,
        *,
        parent_id: str,
        token_key: str,
    ) -> Optional[str]:
        ...


class ScrapeService:
    """Create scrape jobs, persist headers, spawn preview / child scrape jobs."""

    def __init__(
        self,
        store: JobStore,
        scraper: AlbumScraper,
        parser: _ParserLike,
        events: _EventBusLike,
        workspace: Callable[[Path], _WorkspaceLike],
        jobs_root: Path,
        auto_publisher: Optional[_AutoPublisherLike] = None,
        submit: Optional[Callable[[str, Callable[[], None]], None]] = None,
    ) -> None:
        self._store = store
        self._scraper = scraper
        self._parser = parser
        self._events = events
        self._workspace = workspace
        self._jobs_root = Path(jobs_root)
        self._auto_publisher = auto_publisher
        self._submit = submit

    def start(
        self,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        parent_job_id: Optional[str] = None,
        auto_publish: bool = False,
        access_token: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> str:
        token = (access_token or "").strip()
        scrape_url = validate_scrape_url(url)
        header_map: Optional[Dict[str, str]] = None
        if headers:
            header_map = {str(key): str(value) for key, value in headers.items()}
        folder_label = urlparse(scrape_url).netloc or None
        job = self._store.create(
            self._jobs_root,
            job_type=TYPE_SCRAPE,
            folder_label=folder_label,
            scrape_url=scrape_url,
            scrape_headers=header_map,
            parent_job_id=parent_job_id,
            auto_publish=auto_publish,
            import_origin=ORIGIN_WEB,
            owner_id=owner_id,
        )
        if auto_publish and token and self._auto_publisher is not None:
            self._auto_publisher.remember(job.id, token)
        self._events.emit(job.id, "scrape", "Starting scrape")
        preview = self._store.create(
            self._jobs_root,
            job_type=TYPE_PREVIEW,
            parent_job_id=job.id,
            folder_label=folder_label,
            import_origin=ORIGIN_WEB,
        )
        self._events.emit(
            job.id,
            "child",
            preview.id,
            extra={"child_id": preview.id, "type": TYPE_PREVIEW},
        )
        if store_is_cancelled(self._store, job.id) or (
            parent_job_id is not None
            and store_is_cancelled(self._store, parent_job_id)
        ):
            self._store.cancel_if_running(job.id)
            self._store.cancel_if_running(preview.id)
        return job.id

    def finish(self, job_id: str) -> None:
        job = self._store.get(job_id)
        if job.status != STATUS_RUNNING:
            self._store.set_status(job_id, STATUS_RUNNING, job_type=TYPE_SCRAPE)
        scrape_url = job.scrape_url
        headers = dict(job.scrape_headers or {})
        spawn_gallery = job.parent_job_id is None
        try:
            if store_is_cancelled(self._store, job_id):
                raise JobCancelled()
            if not scrape_url:
                raise ValueError("scrape url missing")
            sink = self._download_sink(job_id)
            try:
                raw = self._scraper.scrape(
                    scrape_url,
                    headers=headers,
                    sink=sink,
                    output_dir=job.root,
                )
            except TypeError:
                raw = self._scraper.scrape(
                    scrape_url,
                    headers=headers,
                    sink=sink,
                )
            if store_is_cancelled(self._store, job_id):
                raise JobCancelled()
            result = normalize_scrape_result(raw)
            files = list(result.files)
            if not files and not result.gallery_urls:
                raise ScrapeEmptyError(
                    f"Scrape returned no album files and no child gallery URLs "
                    f"for {scrape_url}. Expected a leaf photo album or a "
                    f"parent/hub that lists child indexes.",
                    url=scrape_url,
                )
            if files:
                self._store.materialize_album(job_id, files)
            if should_spawn_preview_child(files, result.gallery_urls):
                preview_id = self._ensure_preview_child(job, files)
                preview_job = self._store.get(preview_id)
                title = ""
                item_count = 0
                if preview_job.preview is not None:
                    title = preview_job.preview.title
                    item_count = len(preview_job.preview.items)
                self._events.emit(
                    job_id,
                    "child",
                    preview_id,
                    extra={"child_id": preview_id, "type": TYPE_PREVIEW},
                )
                self._events.emit(
                    job_id,
                    "preview_ready",
                    title,
                    extra={
                        "title": title,
                        "items": item_count,
                        "child_id": preview_id,
                    },
                )
                if job.auto_publish and self._auto_publisher is not None:
                    self._auto_publisher.after_preview(
                        preview_id, parent_id=job_id, token_key=job_id
                    )
            else:
                self._discard_unused_preview_children(job_id)
                if job.auto_publish and self._auto_publisher is not None:
                    self._auto_publisher.discard(job_id)
            if spawn_gallery:
                existing_urls = {
                    child.scrape_url
                    for child in self._store.list_children(job_id)
                    if child.type == TYPE_SCRAPE and child.scrape_url
                }
                skip_urls = _skip_done_urls(job)
                for child_url in result.gallery_urls:
                    if store_is_cancelled(self._store, job_id):
                        raise JobCancelled()
                    if child_url in existing_urls or child_url in skip_urls:
                        continue
                    child_id = self.start(
                        child_url,
                        headers=headers,
                        parent_job_id=job_id,
                    )
                    self._events.emit(
                        job_id,
                        "child",
                        child_id,
                        extra={
                            "child_id": child_id,
                            "type": TYPE_SCRAPE,
                            "url": child_url,
                        },
                    )
                    self._enqueue_child(child_id)
                    existing_urls.add(child_url)
            if store_is_cancelled(self._store, job_id):
                raise JobCancelled()
            if self._store.has_active_descendants(job_id):
                self._store.set_status(job_id, STATUS_WAITING, job_type=TYPE_SCRAPE)
                self._events.emit(job_id, "waiting", scrape_url)
            else:
                self._store.set_status(job_id, STATUS_DONE, job_type=TYPE_SCRAPE)
                self._events.emit(job_id, "done", scrape_url)
        except JobCancelled:
            if self._auto_publisher is not None:
                self._auto_publisher.discard(job_id)
            self._mark_cancelled(job_id)
            return
        except Exception as exc:
            if self._auto_publisher is not None:
                self._auto_publisher.discard(job_id)
            code, message = classify_scrape_error(exc, url=scrape_url or "")
            self._fail(job_id, message, error_code=code)
            raise

    def retry(self, job_id: str) -> str:
        job = self._store.get(job_id)
        if job.type != TYPE_SCRAPE:
            raise ValueError("retry is only for scrape jobs")
        if not job.scrape_url:
            raise ValueError("scrape url missing")
        self._events.emit(job_id, "scrape", "Retrying scrape")
        self.finish(job_id)
        return job_id

    def _enqueue_child(self, job_id: str) -> None:
        if store_is_cancelled(self._store, job_id):
            return
        if self._submit is None:
            try:
                self.finish(job_id)
            except JobCancelled:
                raise
            except Exception:
                return
            return
        self._submit(job_id, lambda: self._finish_safe(job_id))

    def _finish_safe(self, job_id: str) -> None:
        try:
            self.finish(job_id)
        except Exception:
            return

    def _fail(
        self,
        job_id: str,
        error: str,
        *,
        error_code: Optional[str] = None,
    ) -> None:
        if store_is_cancelled(self._store, job_id):
            self._mark_cancelled(job_id)
            return
        # Drop or fail the dummy preview before marking the scrape failed so
        # waiters that poll status never observe a leftover preview child.
        if error_code in _CLASSIFIED_SCRAPE_CODES:
            self._discard_unused_preview_children(job_id)
        else:
            self._fail_unused_preview_children(job_id, error)
        self._store.set_status(
            job_id,
            STATUS_FAILED,
            error=error,
            error_code=error_code,
            job_type=TYPE_SCRAPE,
        )
        self._events.emit(job_id, "error", error)

    def _mark_cancelled(self, job_id: str) -> None:
        job = self._store.get(job_id)
        if job.status != STATUS_CANCELLED:
            self._store.set_status(job_id, STATUS_CANCELLED, job_type=TYPE_SCRAPE)
            self._events.emit(job_id, "cancelled", "Job cancelled")
        for child in self._store.list_cancellable_descendants(job_id):
            if self._store.cancel_if_running(child.id):
                self._events.emit(child.id, "cancelled", "Job cancelled")

    def _download_sink(self, job_id: str) -> Any:
        parent_sink = self._events.sink_for(job_id)
        preview_id = next(
            (
                child.id
                for child in self._store.list_children(job_id)
                if child.type == TYPE_PREVIEW
            ),
            None,
        )
        inner: Any = parent_sink
        if preview_id is not None:
            inner = FanOutProgressSink(
                (parent_sink, self._events.sink_for(preview_id))
            )
        return cancellable_sink(inner, self._store, job_id)

    def _fail_unused_preview_children(self, parent_id: str, error: str) -> None:
        for child in self._store.list_children(parent_id):
            if child.type != TYPE_PREVIEW:
                continue
            if child.preview is not None or child.status == STATUS_DONE:
                continue
            self._store.set_status(
                child.id, STATUS_FAILED, error=error, job_type=TYPE_PREVIEW
            )
            self._events.emit(child.id, "error", error)

    def _discard_unused_preview_children(self, parent_id: str) -> None:
        unused = [
            child
            for child in self._store.list_children(parent_id)
            if child.type == TYPE_PREVIEW
            and child.preview is None
            and child.status != STATUS_DONE
        ]
        for child in unused:
            self._store.delete(child.id)

    def _ensure_preview_child(
        self,
        parent: Job,
        files: Any,
    ) -> str:
        existing = [
            child
            for child in self._store.list_children(parent.id)
            if child.type == TYPE_PREVIEW
        ]
        if existing:
            child = existing[0]
        else:
            child = self._store.create(
                self._jobs_root,
                job_type=TYPE_PREVIEW,
                parent_job_id=parent.id,
                folder_label=parent.folder_label,
                import_origin=ORIGIN_WEB,
            )
        if store_is_cancelled(self._store, parent.id) or store_is_cancelled(
            self._store, child.id
        ):
            self._store.cancel_if_running(child.id)
            raise JobCancelled()
        self._store.set_status(child.id, STATUS_RUNNING, job_type=TYPE_PREVIEW)
        self._store.materialize_album(child.id, files)
        preview = self._parser.parse(
            child.root,
            sink=cancellable_sink(
                self._events.sink_for(child.id), self._store, child.id
            ),
        )
        if store_is_cancelled(self._store, child.id):
            raise JobCancelled()
        # Emit before set_preview so status=done observers always see preview_ready.
        self._events.emit(
            child.id,
            "preview_ready",
            preview.title,
            extra={"title": preview.title, "items": len(preview.items)},
        )
        self._store.set_preview(child.id, preview)
        return child.id


def classify_scrape_error(
    exc: BaseException,
    *,
    url: str = "",
) -> tuple[Optional[str], str]:
    """Map scraper exceptions to a stable error_code and readable message.

    Keeps a stable prefix for the UI while appending the original exception
    text when it adds diagnostic detail (HTTP reason, tried URLs, etc.).
    """
    target = str(getattr(exc, "url", "") or url or "").strip()
    original = str(exc).strip()

    def _with_detail(base: str) -> str:
        if not original or original == base:
            return base
        if original in base or base in original:
            # Prefer the longer / more specific string.
            return original if len(original) >= len(base) else base
        return f"{base} — {original}"

    if isinstance(exc, NotArlesGalleryError) or getattr(
        exc, "error_code", None
    ) == ERROR_NOT_ARLES:
        base = f"Not a supported Arles album: {target}".rstrip(": ")
        return ERROR_NOT_ARLES, _with_detail(base)
    if isinstance(exc, ScrapeFetchError) or getattr(
        exc, "error_code", None
    ) == ERROR_FETCH_FAILED:
        status = getattr(exc, "status_code", None)
        if isinstance(status, int):
            where = f": {target}" if target else ""
            base = f"Failed to download gallery{where} (HTTP {status})"
            return ERROR_FETCH_FAILED, _with_detail(base)
        if target:
            return ERROR_FETCH_FAILED, _with_detail(
                f"Failed to download gallery: {target}"
            )
        return ERROR_FETCH_FAILED, original or "Failed to download gallery"
    if isinstance(exc, ScrapeEmptyError) or getattr(
        exc, "error_code", None
    ) == ERROR_SCRAPE_EMPTY:
        base = f"No album photos found: {target}".rstrip(": ")
        return ERROR_SCRAPE_EMPTY, _with_detail(base)
    if original == "scrape returned no files":
        base = f"No album photos found: {target}".rstrip(": ")
        return ERROR_SCRAPE_EMPTY, _with_detail(base)
    return None, original


def _skip_done_urls(job: Job) -> Set[str]:
    extra = job.extra if isinstance(job.extra, dict) else None
    if not extra:
        return set()
    raw = extra.get("skip_done_urls")
    if not isinstance(raw, list):
        return set()
    return {str(url).strip() for url in raw if str(url).strip()}
