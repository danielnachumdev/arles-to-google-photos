"""Re-parse a stored album tree without a new upload."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol

from ..export.parser import STRUCTURE_FALLBACK_WARNING
from ..export.preview import AlbumPreview
from ..export.video_preview import ensure_local_video_previews
from ..progress import JobCancelled
from .cancel import cancellable_sink, store_is_cancelled
from .events import JobEventBus
from .persistence.state import ORIGIN_WEB, infer_import_origin
from .store import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    TYPE_PREVIEW,
    TYPE_SCRAPE,
    TYPE_UPLOAD,
    Job,
    JobNotFoundError,
)

DEFAULT_TITLE_PREFIX = "Reprocessed · "
REPROCESS_MODE_OVERWRITE = "overwrite"
REPROCESS_MODE_NEW = "new"


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

    def set_preview(
        self,
        job_id: str,
        preview: AlbumPreview,
        *,
        warnings: Optional[list[str]] = None,
    ) -> Any:
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


class _ParserLike(Protocol):
    def parse(
        self,
        root: Path,
        sink: Any = None,
        *,
        allow_loose_media: bool = False,
    ) -> AlbumPreview:
        ...


def job_is_web_origin(job: Any) -> bool:
    """True when the job came from a web scrape (explicit or inferred)."""
    origin = infer_import_origin(
        import_origin=getattr(job, "import_origin", None),
        job_type=getattr(job, "type", None),
        parent_job_id=getattr(job, "parent_job_id", None),
        scrape_url=getattr(job, "scrape_url", None),
    )
    return origin == ORIGIN_WEB


def leaf_scrape_id_for_reprocess(store: Any, job: Any) -> Optional[str]:
    """Parent leaf scrape to retry for a web preview, or None.

    Hub scrapes (those with scrape children) are not retried from a preview.
    """
    if getattr(job, "type", None) == TYPE_SCRAPE:
        return str(job.id)
    parent_id = getattr(job, "parent_job_id", None)
    if not parent_id:
        return None
    try:
        parent = store.get(str(parent_id))
    except JobNotFoundError:
        return None
    if getattr(parent, "type", None) != TYPE_SCRAPE:
        return None
    if not getattr(parent, "scrape_url", None):
        return None
    children = store.list_children(parent.id)
    if any(getattr(child, "type", None) == TYPE_SCRAPE for child in children):
        return None
    return str(parent.id)


def resolve_title_prefix(raw: Optional[str]) -> str:
    if raw is None:
        return DEFAULT_TITLE_PREFIX
    return str(raw)


def apply_title_prefix(
    preview: AlbumPreview,
    prefix: str,
    *,
    base_title: Optional[str] = None,
) -> AlbumPreview:
    base = preview.title if base_title is None else base_title
    return replace(preview, title=f"{prefix}{base}")


class _ScrapeStartLike(Protocol):
    def start(
        self,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        parent_job_id: Optional[str] = None,
        auto_publish: bool = False,
        access_token: Optional[str] = None,
    ) -> str:
        ...

    def finish(self, job_id: str) -> None:
        ...


def start_new_preview_reprocess(
    store: Any,
    jobs_root: Path,
    source: Job,
    *,
    title_prefix: str,
    submit: Callable[[str, Callable[[], None]], None],
    reprocess: "ReprocessService",
    scrape: Optional[_ScrapeStartLike] = None,
) -> str:
    """Create a new preview without mutating ``source``.

    Folder (and web-with-files fallback): copy artifacts and parse into a new
    preview id. Web leaf: new scrape+preview lineage from the same URL/headers
    so re-download does not hit the original album.
    """
    prefix = resolve_title_prefix(title_prefix)
    source_preview = getattr(source, "preview", None)
    base_title = source_preview.title if source_preview is not None else ""
    if job_is_web_origin(source) and scrape is not None:
        scrape_svc = scrape
        scrape_id = leaf_scrape_id_for_reprocess(store, source)
        if scrape_id:
            parent = store.get(str(scrape_id))
            scrape_url = getattr(parent, "scrape_url", None)
            if scrape_url:
                new_scrape_id = scrape_svc.start(
                    str(scrape_url),
                    headers=getattr(parent, "scrape_headers", None),
                    auto_publish=bool(getattr(source, "auto_publish", False)),
                )
                preview_child_id = _first_preview_child_id(store, new_scrape_id)
                if preview_child_id is None:
                    raise ValueError("preview child missing")

                def run_web() -> None:
                    scrape_svc.finish(new_scrape_id)
                    child = store.get(preview_child_id)
                    if child.preview is None:
                        return
                    updated = apply_title_prefix(
                        child.preview,
                        prefix,
                        base_title=base_title or child.preview.title,
                    )
                    store.set_preview(preview_child_id, updated)

                submit(new_scrape_id, run_web)
                return preview_child_id

    created = store.create(
        Path(jobs_root),
        job_type=TYPE_PREVIEW,
        folder_label=getattr(source, "folder_label", None),
        auto_publish=bool(getattr(source, "auto_publish", False)),
        import_origin=getattr(source, "import_origin", None),
    )
    store.copy_artifacts(source.id, created.id)
    new_id = str(created.id)
    title_base = base_title or None

    def run_folder() -> None:
        reprocess.reprocess(
            new_id, title_prefix=prefix, title_base=title_base
        )

    if getattr(created, "status", None) != STATUS_PENDING:
        store.set_status(new_id, STATUS_PENDING, job_type=TYPE_PREVIEW)
    submit(new_id, run_folder)
    return new_id


def _first_preview_child_id(store: Any, parent_id: str) -> Optional[str]:
    detail = store.detail_dict(parent_id)
    preview_job_id = detail.get("preview_job_id") if isinstance(detail, dict) else None
    if preview_job_id:
        return str(preview_job_id)
    children = store.list_children(parent_id)
    for child in children:
        if getattr(child, "type", None) == TYPE_PREVIEW:
            return str(child.id)
    return None


class ReprocessService:
    """Run AlbumExportParser on an existing job root and refresh preview."""

    def __init__(
        self,
        store: _StoreLike,
        parser: _ParserLike,
        events: JobEventBus,
    ) -> None:
        self._store = store
        self._parser = parser
        self._events = events

    def reprocess(
        self,
        job_id: str,
        *,
        title_prefix: Optional[str] = None,
        title_base: Optional[str] = None,
    ) -> str:
        try:
            job = self._store.get(job_id)
        except JobNotFoundError:
            raise
        if job.type == TYPE_UPLOAD:
            raise ValueError("reprocess is only for preview jobs")
        try:
            self._store.set_status(
                job.id, STATUS_RUNNING, job_type=TYPE_PREVIEW
            )
            self._events.emit(
                job.id,
                "ingest",
                "Reparsing stored album",
                current=0,
                total=0,
            )
            album_root = self._store.ensure_local_root(job.id)
            ensure_local_video_previews(album_root)
            loose = not job_is_web_origin(job)
            preview = self._parser.parse(
                album_root,
                sink=cancellable_sink(
                    self._events.sink_for(job.id), self._store, job.id
                ),
                allow_loose_media=loose,
            )
            if store_is_cancelled(self._store, job.id):
                raise JobCancelled()
            if title_prefix is not None:
                preview = apply_title_prefix(
                    preview, title_prefix, base_title=title_base
                )
            warnings = (
                [STRUCTURE_FALLBACK_WARNING] if preview.structure_fallback else []
            )
            # Emit before set_preview so status=done observers always see preview_ready.
            self._events.emit(
                job.id,
                "preview_ready",
                preview.title,
                extra={"title": preview.title, "items": len(preview.items)},
            )
            self._store.set_preview(job.id, preview, warnings=warnings)
            return job.id
        except JobCancelled:
            self._store.set_status(
                job.id, STATUS_CANCELLED, job_type=TYPE_PREVIEW
            )
            self._events.emit(job.id, "cancelled", "Job cancelled")
            return job.id
        except Exception as exc:
            if store_is_cancelled(self._store, job.id):
                self._store.set_status(
                    job.id, STATUS_CANCELLED, job_type=TYPE_PREVIEW
                )
                self._events.emit(job.id, "cancelled", "Job cancelled")
                return job.id
            self._store.set_status(
                job.id, STATUS_FAILED, error=str(exc), job_type=TYPE_PREVIEW
            )
            self._events.emit(job.id, "error", str(exc))
            raise
