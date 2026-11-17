"""Streaming multipart album ingress: one file at a time into ArtifactStore.

Avoids a full local staging tree (Cloud Run local disk ≈ memory). Title is
peeked from ``index.html`` among the parts; each part is copied to a temp file,
put into durable storage, then discarded before the next part.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    BinaryIO,
    Callable,
    Dict,
    Iterable,
    Iterator,
    Optional,
    Protocol,
    Sequence,
)

from .ingest import peek_gallery_title
from .store import STATUS_FAILED, TYPE_PREVIEW

STORE_MESSAGE = "Storing files"


@dataclass
class AlbumUploadPart:
    """One multipart file: relative album path + readable stream."""

    relpath: str
    stream: BinaryIO
    mtime: Optional[float] = None


class _IngestLike(Protocol):
    def start(
        self,
        files: Iterable[object] = (),
        *,
        jobs_root: Path,
        overwrite: bool = False,
        auto_publish: bool = False,
        access_token: Optional[str] = None,
        owner_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> str:
        ...

    def finish_prepared(self, job_id: str, *, overwrite: bool = False) -> str:
        ...


class _StoreLike(Protocol):
    def put_album_file(
        self,
        job_id: str,
        relpath: str,
        path: Path,
        mtime: Optional[float] = None,
    ) -> None:
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

    def get(self, job_id: str) -> Any:
        ...

    def update_extra(self, job_id: str, extra: Optional[Dict[str, Any]]) -> Any:
        ...


SubmitFn = Callable[[str, Callable[[], None]], None]
EventsEmitFn = Callable[..., Any]


def peek_gallery_title_from_parts(
    parts: Sequence[AlbumUploadPart],
) -> Optional[str]:
    """Read ``index.html`` from parts (rewinds the stream afterward)."""
    for part in parts:
        name = str(part.relpath).replace("\\", "/").rsplit("/", 1)[-1]
        if name.lower() != "index.html":
            continue
        stream = part.stream
        position = stream.tell() if hasattr(stream, "tell") else 0
        data = stream.read()
        if hasattr(stream, "seek"):
            try:
                stream.seek(position)
            except Exception:
                stream.seek(0)
        if isinstance(data, str):
            data = data.encode("utf-8")
        return peek_gallery_title([(part.relpath, bytes(data), None)])
    return None


class MultipartAlbumIngress:
    """Declarative multipart → durable artifacts → parse (no full staging dir)."""

    def __init__(
        self,
        *,
        store: _StoreLike,
        ingest: _IngestLike,
        jobs_root: Path,
        submit: SubmitFn,
        events_emit: Optional[EventsEmitFn] = None,
    ) -> None:
        self._store = store
        self._ingest = ingest
        self._jobs_root = Path(jobs_root)
        self._submit = submit
        self._emit = events_emit

    def ingest(
        self,
        parts: Sequence[AlbumUploadPart],
        *,
        overwrite: bool = False,
        auto_publish: bool = False,
        access_token: Optional[str] = None,
        owner_id: Optional[str] = None,
        size_meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        job_id = ""
        for event in self.iter_ingest(
            parts,
            overwrite=overwrite,
            auto_publish=auto_publish,
            access_token=access_token,
            owner_id=owner_id,
            size_meta=size_meta,
        ):
            if event.get("event") == "complete":
                job_id = str(event.get("job_id") or "")
        return job_id

    def iter_ingest(
        self,
        parts: Sequence[AlbumUploadPart],
        *,
        overwrite: bool = False,
        auto_publish: bool = False,
        access_token: Optional[str] = None,
        owner_id: Optional[str] = None,
        size_meta: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Store parts one-by-one, yield progress, then enqueue preview prep.

        Yields ``store`` events (current/total) and a final ``complete`` with
        ``job_id``. Preview parse runs via ``submit(finish_prepared)``.
        """
        title = peek_gallery_title_from_parts(parts)
        job_id = self._ingest.start(
            (),
            jobs_root=self._jobs_root,
            overwrite=overwrite,
            auto_publish=auto_publish,
            access_token=access_token,
            owner_id=owner_id,
            title=title,
        )
        if size_meta:
            self._apply_size_meta(job_id, size_meta)
        total = len(parts)
        current_rel = ""
        try:
            for index, part in enumerate(parts, start=1):
                current_rel = str(part.relpath)
                self._accept_part(job_id, part)
                self._emit_store_progress(job_id, index, total)
                yield {
                    "event": "store",
                    "job_id": job_id,
                    "current": index,
                    "total": total,
                    "message": STORE_MESSAGE,
                }
        except Exception as exc:
            where = f" at '{current_rel}'" if current_rel else ""
            message = f"upload store failed{where}: {exc}"
            try:
                self._store.set_status(
                    job_id,
                    STATUS_FAILED,
                    error=message,
                    job_type=TYPE_PREVIEW,
                )
            except Exception:
                pass
            if self._emit is not None:
                try:
                    self._emit(job_id, "error", message)
                except Exception:
                    pass
            raise RuntimeError(message) from exc

        overwrite_flag = overwrite
        self._submit(
            job_id,
            lambda: self._ingest.finish_prepared(
                job_id, overwrite=overwrite_flag
            ),
        )
        yield {"event": "complete", "job_id": job_id}

    def _emit_store_progress(self, job_id: str, current: int, total: int) -> None:
        if self._emit is None:
            return
        self._emit(
            job_id,
            "ingest",
            STORE_MESSAGE,
            current=current,
            total=total,
        )

    def _apply_size_meta(self, job_id: str, size_meta: Dict[str, Any]) -> None:
        from ..export.publish_checkpoint import (
            SIZE_CLASS_KEY,
            merge_extra,
        )

        try:
            current = self._store.get(job_id)
            existing = getattr(current, "extra", None)
        except Exception:
            existing = None
        patch = {
            key: value
            for key, value in size_meta.items()
            if key in {SIZE_CLASS_KEY, "total_bytes", "max_bytes"}
            and value not in (None, "", 0)
        }
        if not patch:
            return
        try:
            self._store.update_extra(job_id, merge_extra(existing, patch))
        except Exception:
            pass

    def _accept_part(self, job_id: str, part: AlbumUploadPart) -> None:
        fd, name = tempfile.mkstemp(prefix="arles-part-", dir=str(self._jobs_root))
        path = Path(name)
        try:
            with os.fdopen(fd, "wb") as out:
                while True:
                    chunk = part.stream.read(1024 * 1024)
                    if not chunk:
                        break
                    if isinstance(chunk, str):
                        chunk = chunk.encode("utf-8")
                    out.write(chunk)
            if part.mtime is not None:
                os.utime(path, (part.mtime, part.mtime))
            self._store.put_album_file(
                job_id, part.relpath, path, mtime=part.mtime
            )
        finally:
            path.unlink(missing_ok=True)
