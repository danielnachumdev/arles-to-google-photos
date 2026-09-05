"""Declarative classification of album relative paths (structure vs media)."""
from __future__ import annotations

from enum import Enum
from pathlib import Path


class ArtifactKind(str, Enum):
    """What an album relative path is for cache / hydrate policy."""

    STRUCTURE = "structure"
    MEDIA = "media"
    STATE = "state"
    OTHER = "other"


class AlbumArtifactClassifier:
    """Classifies Arles export relpaths without I/O.

    Structure files (HTML/CSS) are enough to parse titles, journal, and captions.
    Media (hrimages, thumbnails, …) is durable in object storage and loaded
    on demand so Cloud Run does not keep the whole album in memory-backed disk.
    """

    _STRUCTURE_SUFFIXES = frozenset({".html", ".htm", ".css"})
    _MEDIA_TOP_DIRS = frozenset(
        {"hrimages", "images", "thumbnails", "preview", "icons"}
    )
    _STATE_NAMES = frozenset(
        {
            "job.json",
            "events.json",
            "job.json.tmp",
            "events.json.tmp",
            "arles-media-index.json",
        }
    )

    def classify(self, relpath: str) -> ArtifactKind:
        normalized = (relpath or "").replace("\\", "/").lstrip("/")
        if not normalized:
            return ArtifactKind.OTHER
        name = Path(normalized).name
        if name in self._STATE_NAMES or name.startswith("arles-media-index"):
            return ArtifactKind.STATE
        suffix = Path(normalized).suffix.lower()
        if suffix in self._STRUCTURE_SUFFIXES:
            return ArtifactKind.STRUCTURE
        top = normalized.split("/", 1)[0].casefold()
        if top in self._MEDIA_TOP_DIRS:
            return ArtifactKind.MEDIA
        if suffix in {
            ".jpg",
            ".jpeg",
            ".jpe",
            ".png",
            ".gif",
            ".tif",
            ".tiff",
            ".bmp",
            ".webp",
            ".mp4",
            ".mov",
            ".avi",
            ".m4v",
            ".mpg",
            ".mpeg",
            ".wmv",
        }:
            return ArtifactKind.MEDIA
        return ArtifactKind.OTHER

    def is_structure(self, relpath: str) -> bool:
        return self.classify(relpath) is ArtifactKind.STRUCTURE

    def is_media(self, relpath: str) -> bool:
        return self.classify(relpath) is ArtifactKind.MEDIA

    def retain_locally_after_remote_put(self, relpath: str) -> bool:
        """True when a remote store may keep this file in the scratch cache."""
        return self.is_structure(relpath)
