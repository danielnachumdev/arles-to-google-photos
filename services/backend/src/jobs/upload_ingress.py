"""Streaming multipart album ingress: stage locally, durable store in background.

Avoids blocking the HTTP request on GCS uploads. Each part is copied to a temp
file, staged onto the job's local tree, then discarded. An orchestrator job
flushes staged files to durable storage (with SSE progress) and runs preview
prepare.
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
    List,
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

    def staged_album_root(self, job_id: str) -> Path:
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
    """Multipart → local stage → enqueue durable store + parse."""

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
        """Stage parts locally, enqueue background store+prepare, yield complete.

        Durable GCS put and preview parse run via ``submit(store_and_prepare)``.
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
        try:
            for part in parts:
                self._stage_part(job_id, part)
        except Exception:
            raise

        overwrite_flag = overwrite
        self._submit(
            job_id,
            lambda: self.store_and_prepare(job_id, overwrite=overwrite_flag),
        )
        yield {"event": "complete", "job_id": job_id}

    def store_and_prepare(self, job_id: str, *, overwrite: bool = False) -> str:
        """Flush staged files to durable storage, then parse preview."""
        self._flush_staged(job_id)
        return self._ingest.finish_prepared(job_id, overwrite=overwrite)

    def _flush_staged(self, job_id: str) -> None:
        if self._store.retains_full_local_tree():
            # Filesystem backend: stage already wrote durable local files.
            return
        root = self._store.staged_album_root(job_id)
        skip_names = {
            "job.json",
            "events.json",
            "job.json.tmp",
            "events.json.tmp",
            "arles-media-index.json",
        }
        rels: List[str] = []
        if root.is_dir():
            for path in root.rglob("*"):
                if not path.is_file() or path.name in skip_names:
                    continue
                if path.stat().st_size <= 0:
                    continue
                rels.append(path.relative_to(root).as_posix())
        total = len(rels)
        for index, rel in enumerate(rels, start=1):
            path = root / rel
            if not path.is_file() or path.stat().st_size <= 0:
                continue
            mtime = path.stat().st_mtime
            self._store.put_album_file(job_id, rel, path, mtime=mtime)
            self._emit_store_progress(job_id, index, total)

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

    def _stage_part(self, job_id: str, part: AlbumUploadPart) -> None:
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
            self._store.stage_album_file(
                job_id, part.relpath, path, mtime=part.mtime
            )
        finally:
            path.unlink(missing_ok=True)
