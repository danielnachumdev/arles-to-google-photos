"""Durable per-item Google Photos publish checkpoints on job.extra."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

from .publisher import STATUS_CREATED

PUBLISH_ITEMS_KEY = "publish_items"
PHOTOS_ALBUM_ID_KEY = "photos_album_id"
PHOTOS_ALBUM_URL_KEY = "photos_album_url"
PHOTOS_ALBUM_TITLE_KEY = "photos_album_title"
SIZE_CLASS_KEY = "size_class"

SIZE_SMALL = "small"
SIZE_LARGE = "large"

# LARGE if any file > 256 MiB or total media > 1 GiB
LARGE_ANY_FILE_BYTES = 256 * 1024 * 1024
LARGE_TOTAL_BYTES = 1024 * 1024 * 1024
# Hard ceiling for a single file on 2 GiB Cloud Run until proven otherwise
HARD_FILE_CEILING_BYTES = int(1.5 * 1024 * 1024 * 1024)


def classify_media_sizes(
    *,
    total_bytes: int,
    max_bytes: int,
) -> str:
    if max_bytes > LARGE_ANY_FILE_BYTES or total_bytes > LARGE_TOTAL_BYTES:
        return SIZE_LARGE
    return SIZE_SMALL


def exceeds_hard_file_ceiling(max_bytes: int) -> bool:
    return max_bytes > HARD_FILE_CEILING_BYTES


def publish_items_map(extra: Optional[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not isinstance(extra, Mapping):
        return {}
    raw = extra.get(PUBLISH_ITEMS_KEY)
    if not isinstance(raw, Mapping):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for key, value in raw.items():
        if isinstance(value, Mapping):
            out[str(key)] = dict(value)
    return out


def created_item_ids(extra: Optional[Mapping[str, Any]]) -> List[str]:
    items = publish_items_map(extra)
    return [
        item_id
        for item_id, meta in items.items()
        if str(meta.get("status") or "") == STATUS_CREATED
    ]


def resume_album_fields(
    extra: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, str]]:
    if not isinstance(extra, Mapping):
        return None
    album_id = str(extra.get(PHOTOS_ALBUM_ID_KEY) or "").strip()
    if not album_id:
        return None
    return {
        "album_id": album_id,
        "title": str(extra.get(PHOTOS_ALBUM_TITLE_KEY) or "").strip(),
        "product_url": str(extra.get(PHOTOS_ALBUM_URL_KEY) or "").strip(),
    }


def merge_extra(
    existing: Optional[Mapping[str, Any]],
    patch: Mapping[str, Any],
) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(existing or {})
    for key, value in patch.items():
        if key == PUBLISH_ITEMS_KEY and isinstance(value, Mapping):
            items = publish_items_map(out)
            for item_id, meta in value.items():
                if isinstance(meta, Mapping):
                    items[str(item_id)] = dict(meta)
            out[PUBLISH_ITEMS_KEY] = items
        else:
            out[key] = value
    return out


def checkpoint_item(
    existing: Optional[Mapping[str, Any]],
    item_id: str,
    status: str,
    fields: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    meta = dict(fields or {})
    meta["status"] = status
    return merge_extra(existing, {PUBLISH_ITEMS_KEY: {item_id: meta}})


def copy_created_checkpoints(
    source_extra: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Carry created-item + album checkpoints into a new remaining-mode upload."""
    created = {
        item_id: meta
        for item_id, meta in publish_items_map(source_extra).items()
        if str(meta.get("status") or "") == STATUS_CREATED
    }
    out: Dict[str, Any] = {}
    if created:
        out[PUBLISH_ITEMS_KEY] = created
    album = resume_album_fields(source_extra)
    if album is not None:
        out[PHOTOS_ALBUM_ID_KEY] = album["album_id"]
        if album["title"]:
            out[PHOTOS_ALBUM_TITLE_KEY] = album["title"]
        if album["product_url"]:
            out[PHOTOS_ALBUM_URL_KEY] = album["product_url"]
    if isinstance(source_extra, Mapping) and source_extra.get(SIZE_CLASS_KEY):
        out[SIZE_CLASS_KEY] = source_extra.get(SIZE_CLASS_KEY)
    return out
