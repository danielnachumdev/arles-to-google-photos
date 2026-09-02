"""Immutable preview of an HTML album export (no Google Photos I/O)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Tuple


@dataclass(frozen=True)
class AlbumJournal:
    heading: Optional[str]
    paragraphs: Tuple[str, ...]


@dataclass(frozen=True)
class PreviewItem:
    id: str
    relpath: str
    caption: str
    size_bytes: int
    last_modified: Optional[datetime] = None
    taken_on: Optional[date] = None
    kind: Optional[str] = None
    thumb_relpath: Optional[str] = None
    play_relpath: Optional[str] = None


@dataclass(frozen=True)
class AlbumPreview:
    title: str
    description: Optional[str]
    multi_index: bool
    items: Tuple[PreviewItem, ...]
    journal: Optional[AlbumJournal] = None
    # True when media was imported without a full Arles HTML layout
    # (folder-name title, no journal/gallery HTML metadata guarantees).
    structure_fallback: bool = False
