"""Shared media kind helpers for album preview items."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

KIND_IMAGE = "image"
KIND_VIDEO = "video"

VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mov", ".avi", ".m4v", ".webm", ".mkv", ".wmv", ".mpg", ".mpeg"}
)
IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".bmp"}
)
BROWSER_PLAYABLE_VIDEO = frozenset({".mp4", ".m4v", ".webm"})


def id_from_hr_stem(stem: str) -> str:
    """Strip a trailing ``hr`` from an hrimages stem (case-insensitive)."""
    if len(stem) > 2 and stem.lower().endswith("hr"):
        return stem[:-2]
    return stem


_LOOSE_SMALL_STEM = re.compile(r"^(?P<base>.+?)_(?:small|Small)(?:_|$)")


def normalize_loose_stem(stem: str) -> str:
    """Normalize legacy stems (``*hr``, ``*_small_*``, ``*_Big``) to a stable item id."""
    text = id_from_hr_stem(stem)
    if len(text) > 4 and text.lower().endswith("_big"):
        text = text[:-4]
    match = _LOOSE_SMALL_STEM.match(text)
    if match is not None:
        text = match.group("base")
    return text


_MEDIA_FILENAME = re.compile(
    r"\.(jpe?g|png|gif|tiff?|bmp|webp|mp4|mov|avi|wmv|m4v|webm|mkv)$",
    re.IGNORECASE,
)


def looks_like_media_filename(text: str) -> bool:
    """True when text is a bare media filename (common Arles ``<title>`` on image viewers)."""
    return bool(_MEDIA_FILENAME.search(str(text or "").strip()))


def is_video_filename(name: str) -> bool:
    return Path(name).suffix.lower() in VIDEO_EXTENSIONS


def infer_item_kind(relpath: str, kind: Optional[str] = None) -> str:
    """Return ``image`` or ``video``. Unset kind is inferred from the relpath suffix."""
    raw = str(kind or "").strip().lower()
    if raw in {KIND_IMAGE, KIND_VIDEO}:
        return raw
    return KIND_VIDEO if is_video_filename(relpath) else KIND_IMAGE
