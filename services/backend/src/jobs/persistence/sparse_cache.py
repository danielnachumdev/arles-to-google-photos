"""Sparse local scratch for remote artifact stores (Cloud Run memory-safe)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

from ...export.media_index import MediaIndex
from .album_paths import AlbumArtifactClassifier, ArtifactKind


class SparseAlbumWorkspace:
    """Builds a parse-ready local tree without holding media bytes.

    Structure files are real. Media paths are empty placeholders plus a
    :class:`~src.export.media_index.MediaIndex` so the parser can report
    size/mtime correctly.
    """

    def __init__(
        self,
        root: Path,
        *,
        classifier: Optional[AlbumArtifactClassifier] = None,
    ) -> None:
        self.root = Path(root)
        self._classifier = classifier or AlbumArtifactClassifier()

    def place_structure_file(self, relpath: str, data: bytes) -> Path:
        dest = self._dest(relpath)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest

    def place_media_placeholder(
        self,
        relpath: str,
        *,
        size_bytes: int,
        mtime: Optional[float] = None,
    ) -> Path:
        del size_bytes  # recorded in MediaIndex; placeholder stays empty
        dest = self._dest(relpath)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"")
        if mtime is not None:
            os.utime(dest, (mtime, mtime))
        return dest

    def write_media_index(self, index: MediaIndex) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return index.write(self.root)

    def discard_media_bodies(self, relpaths: Iterable[str]) -> None:
        """Remove local media bytes after a remote put (keep structure)."""
        for relpath in relpaths:
            if not self._classifier.is_media(relpath):
                continue
            path = self.root / relpath
            if path.is_file():
                path.unlink()

    def _dest(self, relpath: str) -> Path:
        normalized = relpath.replace("\\", "/").lstrip("/")
        parts = [p for p in normalized.split("/") if p and p != "."]
        if not parts or any(p == ".." for p in parts):
            raise ValueError(f"path traversal rejected: {relpath}")
        return self.root.joinpath(*parts)

    def kind(self, relpath: str) -> ArtifactKind:
        return self._classifier.classify(relpath)
