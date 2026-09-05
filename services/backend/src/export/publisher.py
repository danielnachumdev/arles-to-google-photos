"""Publish an AlbumPreview to Google Photos (no HTML parsing)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Protocol, Sequence

from gp_wrapper import (
    MEDIA_ITEM_BATCH_CREATE_MAXIMUM_IDS,
    Album,
    AlbumPosition,
    GooglePhotos,
    MediaItem,
    NewMediaItem,
    PositionType,
    SimpleMediaItem,
)

from ..progress import ProgressSink, raise_if_cancelled
from ..utils import batchify
from .preview import AlbumJournal, AlbumPreview, PreviewItem
from .timestamps import CaptureTimestampStamper

PathResolver = Callable[[str], Path]
PathReleaser = Callable[[str], None]


class _StamperLike(Protocol):
    def album_day_for(
        self,
        root: Path,
        items: Sequence[PreviewItem],
        *,
        resolve: Optional[PathResolver] = None,
    ) -> Optional[object]:
        ...

    def stamp_path(
        self,
        path: Path,
        item: PreviewItem,
        *,
        index: int,
        prev: Optional[object],
        album_day: Optional[object],
        root: Path,
    ) -> Optional[object]:
        ...


class AlbumPublisher:
    """Create a Photos album and attach preview media via gp_wrapper."""

    def __init__(self, stamper: Optional[_StamperLike] = None) -> None:
        self._stamper = stamper or CaptureTimestampStamper()

    def publish(
        self,
        gp: GooglePhotos,
        root: Path,
        preview: AlbumPreview,
        sink: Optional[ProgressSink] = None,
        *,
        resolve: Optional[PathResolver] = None,
        release: Optional[PathReleaser] = None,
    ) -> Album:
        root = Path(root)
        resolve_path = resolve or (lambda rel: root / rel)
        to_upload = list(preview.items)
        total = len(to_upload)
        if sink is not None:
            sink.emit("publish", "Creating album", current=0, total=max(total, 1))

        album = _create_album(gp, preview.title)
        if preview.description:
            album.add_text([preview.description])
        # FIRST_IN_ALBUM inserts at the start, so later calls sit higher:
        # heading (top) → body → gallery description → photos.
        body_parts = _journal_body_parts(preview.journal)
        if body_parts is not None:
            album.add_text(
                body_parts,
                relative_position=PositionType.FIRST_IN_ALBUM,
            )
        heading_parts = _journal_heading_parts(preview.journal)
        if heading_parts is not None:
            album.add_text(
                heading_parts,
                relative_position=PositionType.FIRST_IN_ALBUM,
            )

        # Prefer taken_on from preview ids; do not resolve media just to sniff EXIF.
        album_day = self._stamper.album_day_for(root, to_upload)
        prev = None
        last_id: Optional[str] = None
        done = 0
        for batch_items in batchify(to_upload, MEDIA_ITEM_BATCH_CREATE_MAXIMUM_IDS):
            raise_if_cancelled(sink)
            new_items: List[NewMediaItem] = []
            for item in batch_items:
                raise_if_cancelled(sink)
                absolute_index = done
                path = resolve_path(item.relpath)
                prev = self._stamper.stamp_path(
                    path,
                    item,
                    index=absolute_index,
                    prev=prev,
                    album_day=album_day,
                    root=root,
                )
                done += 1
                token = MediaItem.upload_media(gp, str(path))
                new_items.append(
                    NewMediaItem(item.caption, SimpleMediaItem(token, item.id))
                )
                if release is not None:
                    release(item.relpath)
                if sink is not None:
                    sink.emit("publish", item.relpath, current=done, total=total)
            if last_id is None:
                position = AlbumPosition(PositionType.LAST_IN_ALBUM)
            else:
                position = AlbumPosition(
                    PositionType.AFTER_MEDIA_ITEM,
                    relativeMediaItemId=last_id,
                )
            results = MediaItem.batchCreate(gp, new_items, album.id, position)
            last_id = _last_created_media_id(results) or last_id
        return album


_ADD_TEXT_PART_LIMIT = 1000


def _create_album(gp: GooglePhotos, title: str) -> Album:
    """Create a Photos album; surface API failures that gp_wrapper masks as KeyError('id')."""
    try:
        return Album.create(gp, title)
    except KeyError as exc:
        if exc.args and exc.args[0] == "id":
            raise RuntimeError(
                "Google Photos album create failed (API response missing album id; "
                "often an expired/invalid access token, missing Photos scope, or "
                "a Photos API error). Sign in again and retry."
            ) from exc
        raise


def _chunk_text(text: str, limit: int = _ADD_TEXT_PART_LIMIT) -> List[str]:
    """Split text so each gp_wrapper add_text part stays within Google's limit."""
    if not text:
        return []
    return [text[i:i + limit] for i in range(0, len(text), limit)]


def _journal_heading_parts(journal: Optional[AlbumJournal]) -> Optional[List[str]]:
    """Heading only — its own Photos text block (short text is centered ≈ title)."""
    if journal is None:
        return None
    heading = (journal.heading or "").strip()
    if not heading:
        return None
    return _chunk_text(heading)


def _journal_body_parts(journal: Optional[AlbumJournal]) -> Optional[List[str]]:
    """Paragraphs as one add_text (blank-line separators), no heading."""
    if journal is None:
        return None
    paragraphs = [p.strip() for p in journal.paragraphs if p and p.strip()]
    if not paragraphs:
        return None
    parts: List[str] = []
    for paragraph in paragraphs:
        if parts:
            parts.append("\n\n")
        parts.extend(_chunk_text(paragraph))
    return parts


def _last_created_media_id(results: Sequence[object]) -> Optional[str]:
    for result in reversed(list(results)):
        media = getattr(result, "mediaItem", None)
        item_id = getattr(media, "id", None) if media is not None else None
        if item_id:
            return str(item_id)
    return None
