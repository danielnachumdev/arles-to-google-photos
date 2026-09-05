"""Streaming multipart album ingress: one part at a time into ArtifactStore.

Avoids a full local staging tree (Cloud Run local disk ≈ memory). Title is
peeked from ``index.html`` among the parts; each part is copied to a temp file,
put into durable storage, then discarded before the next part.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Iterable, Optional, Protocol, Sequence

from .ingest import peek_gallery_title


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


SubmitFn = Callable[[str, Callable[[], None]], None]


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
    ) -> None:
        self._store = store
        self._ingest = ingest
        self._jobs_root = Path(jobs_root)
        self._submit = submit

    def ingest(
        self,
        parts: Sequence[AlbumUploadPart],
        *,
        overwrite: bool = False,
        auto_publish: bool = False,
        access_token: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> str:
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
                self._accept_part(job_id, part)
        except Exception:
            # Best-effort: caller / start already created the job; leave cleanup
            # to normal failed-job paths. Do not keep partial staging dirs.
            raise

        overwrite_flag = overwrite
        self._submit(
            job_id,
            lambda: self._ingest.finish_prepared(
                job_id, overwrite=overwrite_flag
            ),
        )
        return job_id

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
