"""Ingest uploaded album trees: workspace → parse → preview done."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol, Tuple

from bs4 import BeautifulSoup
from bs4.element import Tag

from ..export.parser import STRUCTURE_FALLBACK_WARNING
from ..export.preview import AlbumPreview
from ..export.video_preview import ensure_local_video_previews
from ..progress import JobCancelled
from .cancel import cancellable_sink, store_is_cancelled
from .events import AUDIENCE_UI, KIND_LOG
from .store import (
    EVENTS_NAME,
    JOB_META_NAME,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    TYPE_PREVIEW,
)

FileTuple = Tuple[str, bytes, Optional[float]]


def peek_gallery_title(files: Iterable[FileTuple]) -> Optional[str]:
    """Best-effort `.gallerytitle` from uploaded ``index.html`` bytes."""
    for relpath, data, _mtime in files:
        name = str(relpath).replace("\\", "/").rsplit("/", 1)[-1]
        if name.lower() != "index.html":
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")
        soup = BeautifulSoup(text, features="html.parser")
        title_el = soup.find("span", class_="gallerytitle")
        if isinstance(title_el, Tag) and title_el.get_text(strip=True):
            cleaned = title_el.get_text().replace("\xa0", " ")
            title = " ".join(cleaned.split())
            return title or None
        return None
    return None


def peek_gallery_title_from_dir(root: Path) -> Optional[str]:
    """Best-effort `.gallerytitle` from ``index.html`` on disk (staged upload)."""
    root = Path(root)
    candidates = [root / "index.html"]
    candidates.extend(
        path
        for path in root.rglob("index.html")
        if path != candidates[0]
    )
    for index_path in candidates:
        if not index_path.is_file():
            continue
        return peek_gallery_title(
            [("index.html", index_path.read_bytes(), None)]
        )
    return None


def iter_files_from_dir(root: Path) -> Iterable[FileTuple]:
    """Yield ``(relpath, bytes, mtime)`` one file at a time from a staging dir."""
    root = Path(root)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        yield rel, path.read_bytes(), path.stat().st_mtime


class AlbumExistsError(Exception):
    """Another job already uses this gallery title; caller must confirm overwrite."""

    def __init__(self, existing_id: str, title: str) -> None:
        self.existing_id = existing_id
        self.title = title
        super().__init__(f"Album already exists: {title}")


class _JobLike(Protocol):
    id: str
    root: Path
    status: str


class _StoreLike(Protocol):
    def create(self, base_dir: Path, *, auto_publish: bool = False) -> _JobLike:
        ...

    def get(self, job_id: str) -> _JobLike:
        ...

    def materialize_album(
        self,
        job_id: str,
        files: Iterable[tuple[str, bytes, Optional[float]]],
    ) -> Path:
        ...

    def find_by_title(
        self, title: str, *, owner_id: Optional[str] = None
    ) -> Optional[_JobLike]:
        ...

    def delete(self, job_id: str) -> None:
        ...

    def delete_duplicates_for_title(
        self, title: str, *, keep_id: str, owner_id: Optional[str] = None
    ) -> None:
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


class _WorkspaceLike(Protocol):
    def materialize(
        self, files: Iterable[tuple[str, bytes, Optional[float]]]
    ) -> Path:
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


def _preview_warnings(preview: AlbumPreview) -> list[str]:
    if preview.structure_fallback:
        return [STRUCTURE_FALLBACK_WARNING]
    return []


def _overwrite_album_tree(
    job_id: str,
    files: Iterable[tuple[str, bytes, Optional[float]]],
    store: "_StoreLike",
) -> None:
    job = store.get(job_id)
    root = job.root
    if root.is_dir():
        for child in list(root.iterdir()):
            if child.name in {
                JOB_META_NAME,
                f"{JOB_META_NAME}.tmp",
                EVENTS_NAME,
                f"{EVENTS_NAME}.tmp",
            }:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    store.materialize_album(job_id, files)


class _BoundProgressSink:
    """Adapt EventBus.emit(job_id, ...) to ProgressSink.emit(...)."""

    def __init__(self, events: _EventBusLike, job_id: str) -> None:
        self._events = events
        self._job_id = job_id

    def emit(
        self,
        stage: str,
        message: str = "",
        *,
        current: int = 0,
        total: int = 0,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self._events.emit(
            self._job_id,
            stage,
            message,
            current=current,
            total=total,
            extra=dict(extra) if extra is not None else None,
            kind=KIND_LOG,
            audience=AUDIENCE_UI,
        )


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


class IngestService:
    """Create a job, materialize upload, parse preview, record result."""

    def __init__(
        self,
        store: _StoreLike,
        parser: _ParserLike,
        events: _EventBusLike,
        workspace: Callable[[Path], _WorkspaceLike],
        auto_publisher: Optional[_AutoPublisherLike] = None,
    ) -> None:
        self._store = store
        self._parser = parser
        self._events = events
        self._workspace = workspace
        self._auto_publisher = auto_publisher

    def ingest(
        self,
        files: Iterable[tuple[str, bytes, Optional[float]]],
        *,
        jobs_root: Path,
        overwrite: bool = False,
        auto_publish: bool = False,
        access_token: Optional[str] = None,
    ) -> str:
        file_list = list(files)
        job_id = self.start(
            file_list,
            jobs_root=jobs_root,
            overwrite=overwrite,
            auto_publish=auto_publish,
            access_token=access_token,
        )
        return self.finish(job_id, file_list, overwrite=overwrite)

    def start(
        self,
        files: Iterable[tuple[str, bytes, Optional[float]]] = (),
        *,
        jobs_root: Path,
        overwrite: bool = False,
        auto_publish: bool = False,
        access_token: Optional[str] = None,
        owner_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> str:
        if auto_publish:
            token = (access_token or "").strip()
            if not token:
                raise ValueError("google access token required")
        file_list = list(files)
        if title is None:
            title = peek_gallery_title(file_list)
        existing = (
            self._store.find_by_title(title, owner_id=owner_id) if title else None
        )
        if existing is not None and not overwrite:
            raise AlbumExistsError(existing_id=existing.id, title=title or "")
        if existing is not None and overwrite:
            job_id = existing.id
            if existing.status not in (STATUS_PENDING, STATUS_RUNNING):
                self._store.set_status(
                    job_id, STATUS_PENDING, job_type=TYPE_PREVIEW
                )
        elif auto_publish:
            job_id = self._store.create(
                Path(jobs_root), auto_publish=True, owner_id=owner_id
            ).id
        else:
            job_id = self._store.create(Path(jobs_root), owner_id=owner_id).id
        if auto_publish and self._auto_publisher is not None:
            self._auto_publisher.remember(job_id, (access_token or "").strip())
        return job_id

    def finish(
        self,
        job_id: str,
        files: Iterable[tuple[str, bytes, Optional[float]]],
        *,
        overwrite: bool = False,
    ) -> str:
        job = self._store.get(job_id)
        token_key = job_id
        try:
            result_id = self._run(job, files, overwrite=overwrite)
            if self._auto_publisher is not None:
                self._auto_publisher.after_preview(
                    result_id, parent_id=result_id, token_key=token_key
                )
            return result_id
        except AlbumExistsError:
            if self._auto_publisher is not None:
                self._auto_publisher.discard(token_key)
            raise
        except JobCancelled:
            if self._auto_publisher is not None:
                self._auto_publisher.discard(token_key)
            self._mark_cancelled(job_id)
            return job_id
        except Exception as exc:
            if self._auto_publisher is not None:
                self._auto_publisher.discard(token_key)
            if store_is_cancelled(self._store, job_id):
                self._mark_cancelled(job_id)
                return job_id
            self._store.set_status(
                job_id, STATUS_FAILED, error=str(exc), job_type=TYPE_PREVIEW
            )
            self._events.emit(job_id, "error", str(exc))
            raise

    def finish_from_directory(
        self,
        job_id: str,
        staging_dir: Path,
        *,
        overwrite: bool = False,
    ) -> str:
        """Materialize from a disk staging tree (one file in RAM at a time), then parse."""
        staging = Path(staging_dir)
        try:
            paths = [path for path in sorted(staging.rglob("*")) if path.is_file()]

            class _DirFiles:
                def __len__(self) -> int:
                    return len(paths)

                def __iter__(self):
                    for path in paths:
                        rel = path.relative_to(staging).as_posix()
                        yield rel, path.read_bytes(), path.stat().st_mtime

            return self.finish(job_id, _DirFiles(), overwrite=overwrite)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _run(
        self,
        job: _JobLike,
        files: Iterable[tuple[str, bytes, Optional[float]]],
        *,
        overwrite: bool = False,
    ) -> str:
        if job.status != STATUS_RUNNING:
            self._store.set_status(job.id, STATUS_RUNNING, job_type=TYPE_PREVIEW)
        if store_is_cancelled(self._store, job.id):
            raise JobCancelled()
        # Prefer sized collections so progress totals work; avoid list(generator)
        # which would load the whole album into RAM.
        if isinstance(files, (list, tuple)):
            total = len(files)
            file_list: Iterable[tuple[str, bytes, Optional[float]]] = files
            overwrite_files: Iterable[tuple[str, bytes, Optional[float]]] = files
        elif hasattr(files, "__len__") and hasattr(files, "__iter__"):
            total = len(files)  # type: ignore[arg-type]
            file_list = files
            overwrite_files = files
        else:
            total = 0
            file_list = files
            overwrite_files = ()
        self._events.emit(
            job.id, "ingest", "Writing upload", current=0, total=total
        )
        self._store.materialize_album(job.id, file_list)
        self._events.emit(
            job.id, "ingest", "Upload written", current=total, total=total
        )
        if store_is_cancelled(self._store, job.id):
            raise JobCancelled()

        ensure_local_video_previews(job.root)
        preview = self._parser.parse(
            job.root,
            sink=cancellable_sink(
                _BoundProgressSink(self._events, job.id), self._store, job.id
            ),
            allow_loose_media=True,
        )
        if store_is_cancelled(self._store, job.id):
            raise JobCancelled()
        existing = self._store.find_by_title(
            preview.title, owner_id=getattr(job, "owner_id", None)
        )
        warnings = _preview_warnings(preview)
        if existing is not None and existing.id != job.id:
            if not overwrite:
                self._store.delete(job.id)
                raise AlbumExistsError(
                    existing_id=existing.id, title=preview.title
                )
            if not overwrite_files:
                overwrite_files = iter_files_from_dir(job.root)
            _overwrite_album_tree(existing.id, overwrite_files, self._store)
            # Emit before set_preview so status=done observers always see preview_ready.
            self._events.emit(
                existing.id,
                "preview_ready",
                preview.title,
                extra={"title": preview.title, "items": len(preview.items)},
            )
            self._store.set_preview(existing.id, preview, warnings=warnings)
            self._store.delete(job.id)
            self._store.delete_duplicates_for_title(
                preview.title,
                keep_id=existing.id,
                owner_id=getattr(job, "owner_id", None),
            )
            return existing.id

        # Emit before set_preview so status=done observers always see preview_ready.
        self._events.emit(
            job.id,
            "preview_ready",
            preview.title,
            extra={"title": preview.title, "items": len(preview.items)},
        )
        self._store.set_preview(job.id, preview, warnings=warnings)
        return job.id

    def _mark_cancelled(self, job_id: str) -> None:
        self._store.set_status(job_id, STATUS_CANCELLED, job_type=TYPE_PREVIEW)
        self._events.emit(job_id, "cancelled", "Job cancelled")

