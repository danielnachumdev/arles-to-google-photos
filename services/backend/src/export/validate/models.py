"""Validation report and side indexes (remote Arles vs Photos)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RemoteItemSnapshot:
    item_id: str
    caption: str
    byte_size: Optional[int]
    media_url: Optional[str] = None


@dataclass(frozen=True)
class RemoteAlbumSnapshot:
    title_id: str
    title: str
    url: str
    items: tuple[RemoteItemSnapshot, ...] = ()


@dataclass(frozen=True)
class PhotosItemSnapshot:
    item_id: str
    filename: str
    caption: str
    byte_size: Optional[int]
    media_item_id: str = ""


@dataclass(frozen=True)
class PhotosAlbumSnapshot:
    title_id: str
    title: str
    album_id: str
    product_url: str
    items: tuple[PhotosItemSnapshot, ...] = ()


@dataclass
class ItemMismatch:
    item_id: str
    field: str
    remote: Any = None
    photos: Any = None


@dataclass
class MatchedAlbumReport:
    title_id: str
    title: str
    remote_url: str
    photos_album_id: str
    photos_product_url: str
    identical: bool
    only_remote_items: List[str] = field(default_factory=list)
    only_photos_items: List[str] = field(default_factory=list)
    mismatches: List[ItemMismatch] = field(default_factory=list)


@dataclass
class SideAlbumRef:
    title_id: str
    title: str
    item_count: int
    url: Optional[str] = None
    album_id: Optional[str] = None
    product_url: Optional[str] = None


@dataclass
class ValidationReport:
    root_url: str
    identical: bool
    summary: Dict[str, int]
    warnings: List[str] = field(default_factory=list)
    matched: List[MatchedAlbumReport] = field(default_factory=list)
    only_remote: List[SideAlbumRef] = field(default_factory=list)
    only_photos: List[SideAlbumRef] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
