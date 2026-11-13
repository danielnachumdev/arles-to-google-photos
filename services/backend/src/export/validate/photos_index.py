"""Index app-created Google Photos albums for validation."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple

from ...progress import ProgressSink, emit_progress, raise_if_cancelled
from ..work_lane import AdaptiveWorkLane, TransientError
from .models import PhotosAlbumSnapshot, PhotosItemSnapshot
from .titles import assign_title_ids


def _photos_is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (TransientError, TimeoutError, ConnectionError)):
        return True
    name = type(exc).__name__.lower()
    if "timeout" in name or "connection" in name:
        return True
    status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    try:
        return int(status) in {408, 429, 500, 502, 503, 504}
    except (TypeError, ValueError):
        return False


class PhotosAlbumIndexer:
    """List app-created albums and probe item captions + byte sizes."""

    def __init__(
        self,
        *,
        lane: Optional[AdaptiveWorkLane] = None,
        max_workers: int = 8,
    ) -> None:
        self._lane = lane
        self._max_workers = max_workers

    def index(
        self,
        gp: Any,
        *,
        sink: ProgressSink | None = None,
    ) -> Tuple[List[PhotosAlbumSnapshot], List[str]]:
        from gpsdk import Album, MediaItem

        albums_raw: List[Any] = list(
            Album.all_albums(gp, excludeNonAppCreatedData=True)
        )
        warnings: List[str] = []
        built: List[Tuple[str, Any, Tuple[PhotosItemSnapshot, ...]]] = []
        total = len(albums_raw)
        own_lane = self._lane is None
        lane = self._lane or AdaptiveWorkLane(
            max_workers=self._max_workers,
            is_transient=_photos_is_transient,
        )
        try:
            for i, album in enumerate(albums_raw, start=1):
                raise_if_cancelled(sink)
                title = str(getattr(album, "title", "") or "")
                emit_progress(
                    sink,
                    stage="photos",
                    message=f"Indexing Photos album: {title or album.id}",
                    current=i,
                    total=max(total, 1),
                )
                items = self._album_items(
                    gp, album, MediaItem, sink=sink, warnings=warnings, lane=lane
                )
                built.append((title, album, tuple(items)))
        finally:
            if own_lane:
                lane.close(wait=True)

        title_ids, collision_warnings = assign_title_ids(
            [title for title, _album, _items in built]
        )
        warnings.extend(collision_warnings)
        snapshots = [
            PhotosAlbumSnapshot(
                title_id=title_ids[i],
                title=title,
                album_id=str(album.id),
                product_url=str(getattr(album, "productUrl", "") or ""),
                items=items,
            )
            for i, (title, album, items) in enumerate(built)
        ]
        return snapshots, warnings

    def _album_items(
        self,
        gp: Any,
        album: Any,
        MediaItem: Any,
        *,
        sink: ProgressSink | None,
        warnings: List[str],
        lane: AdaptiveWorkLane,
    ) -> List[PhotosItemSnapshot]:
        media_list = list(MediaItem.search_all(gp, albumId=album.id, pageSize=50))
        raise_if_cancelled(sink)

        def probe(media: Any) -> PhotosItemSnapshot:
            filename = str(getattr(media, "filename", "") or "")
            item_id = _item_id_from_filename(filename)
            emit_progress(
                sink,
                stage="photos",
                message=f"Starting Photos size probe {item_id or filename}",
            )
            caption = str(getattr(media, "description", "") or "").strip()
            size: Optional[int]
            try:
                size = media.byte_size()
            except Exception as exc:  # noqa: BLE001
                if _photos_is_transient(exc):
                    raise TransientError(str(exc)) from exc
                size = None
            return PhotosItemSnapshot(
                item_id=item_id,
                filename=filename,
                caption=caption,
                byte_size=size,
                media_item_id=str(getattr(media, "id", "") or ""),
            )

        items = lane.map([lambda m=media: probe(m) for media in media_list])
        for item in items:
            if item.byte_size is None:
                warnings.append(
                    f"size_unavailable for Photos item "
                    f"{item.item_id or item.filename}"
                )
        return items


def _item_id_from_filename(filename: str) -> str:
    name = (filename or "").strip()
    if not name:
        return ""
    stem = Path(name).stem
    return stem or name
