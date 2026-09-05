"""Streaming multipart album ingress into ArtifactStore.

Cloud Run local disk counts toward memory, so cloud backends durable-put each
part during the request (one file at a time, then discard). Filesystem backends
stage locally and enqueue preview prepare only. Preview parse always runs via
``submit(finish_prepared)`` after the HTTP response can return.
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
    def stage_album_file(
        self,
        job_id: str,
        relpath: str,
        path: Path,
        mtime: Optional[float] = None,
    ) -> None:
        ...

    def put_album_file(
        self,
        job_id: str,
        relpath: str,
        path: Path,
        mtime: Optional[float] = None,
    ) -> None:
        ...

    def retains_full_local_tree(self) -> bool:
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
    """Multipart → durable artifacts (memory-safe on cloud) → enqueue parse."""

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
    ) -> str:
        job_id = ""
        for event in self.iter_ingest(
            parts,
            overwrite=overwrite,
            auto_publish=auto_publish,
            access_token=access_token,
            owner_id=owner_id,
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
    ) -> Iterator[Dict[str, Any]]:
        """Accept parts, yield optional store progress, enqueue preview prepare.

        Cloud (GCS): each part is uploaded to durable storage during the request
        so the container never holds a full album tree (Cloud Run OOM).

        Local FS: parts are staged on disk; durable store is already local.

        Preview parse always runs in the background via ``submit``.
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
        total = len(parts)
        cloud = not self._store.retains_full_local_tree()
        try:
            for index, part in enumerate(parts, start=1):
                self._accept_part(job_id, part, durable=cloud)
                if cloud:
                    self._emit_store_progress(job_id, index, total)
                    yield {
                        "event": "store",
                        "job_id": job_id,
                        "current": index,
                        "total": total,
                        "message": STORE_MESSAGE,
                    }
        except Exception:
            raise

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

    def _accept_part(
        self, job_id: str, part: AlbumUploadPart, *, durable: bool
    ) -> None:
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
            if durable:
                # GCS: upload immediately, then discard local bytes (placeholder).
                self._store.put_album_file(
                    job_id, part.relpath, path, mtime=part.mtime
                )
            else:
                self._store.stage_album_file(
                    job_id, part.relpath, path, mtime=part.mtime
                )
        finally:
            path.unlink(missing_ok=True)
