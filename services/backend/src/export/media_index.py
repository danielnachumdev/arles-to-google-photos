"""Optional on-disk media size/mtime index for sparse album scratch pads."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional

MEDIA_INDEX_NAME = "arles-media-index.json"


@dataclass(frozen=True)
class MediaIndexEntry:
    size_bytes: int
    mtime: Optional[float] = None


class MediaIndex:
    """Map of media relpath → size/mtime when local files are placeholders."""

    def __init__(self, entries: Optional[Mapping[str, MediaIndexEntry]] = None) -> None:
        self._entries: Dict[str, MediaIndexEntry] = dict(entries or {})

    def get(self, relpath: str) -> Optional[MediaIndexEntry]:
        return self._entries.get(relpath)

    def put(self, relpath: str, entry: MediaIndexEntry) -> None:
        self._entries[relpath] = entry

    def update(self, entries: Mapping[str, MediaIndexEntry]) -> None:
        self._entries.update(entries)

    def to_dict(self) -> Dict[str, Dict[str, object]]:
        out: Dict[str, Dict[str, object]] = {}
        for rel, entry in sorted(self._entries.items()):
            payload: Dict[str, object] = {"size_bytes": int(entry.size_bytes)}
            if entry.mtime is not None:
                payload["mtime"] = float(entry.mtime)
            out[rel] = payload
        return out

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "MediaIndex":
        entries: Dict[str, MediaIndexEntry] = {}
        for rel, value in raw.items():
            if not isinstance(value, Mapping):
                continue
            size = int(value.get("size_bytes") or 0)
            mtime_raw = value.get("mtime")
            mtime = float(mtime_raw) if mtime_raw is not None else None
            entries[str(rel)] = MediaIndexEntry(size_bytes=size, mtime=mtime)
        return cls(entries)

    def write(self, root: Path) -> Path:
        path = Path(root) / MEDIA_INDEX_NAME
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    @classmethod
    def read(cls, root: Path) -> "MediaIndex":
        path = Path(root) / MEDIA_INDEX_NAME
        if not path.is_file():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return cls()
        return cls.from_dict(raw)


_INDEX_CACHE: Dict[str, MediaIndex] = {}


def media_index_entry(root: Path, relpath: str) -> Optional[MediaIndexEntry]:
    """Load (cached per root) media index entry for ``relpath``."""
    key = str(Path(root).resolve())
    if key not in _INDEX_CACHE:
        _INDEX_CACHE[key] = MediaIndex.read(root)
    return _INDEX_CACHE[key].get(relpath)


def clear_media_index_cache() -> None:
    _INDEX_CACHE.clear()
