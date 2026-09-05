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
from .publish_media import PublishMediaPreparer
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

    def __init__(
        self,
        stamper: Optional[_StamperLike] = None,
        *,
        media: Optional[PublishMediaPreparer] = None,
    ) -> None:
        self._stamper = stamper or CaptureTimestampStamper()
        self._media = media or PublishMediaPreparer()

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
            _photos_step(
                "add_text (gallery description)",
                lambda: album.add_text([preview.description]),
            )
        # FIRST_IN_ALBUM inserts at the start, so later calls sit higher:
        # heading (top) → body → gallery description → photos.
        body_parts = _journal_body_parts(preview.journal)
        if body_parts is not None:
            _photos_step(
                "add_text (journal body)",
                lambda: album.add_text(
                    body_parts,
                    relative_position=PositionType.FIRST_IN_ALBUM,
                ),
            )
        heading_parts = _journal_heading_parts(preview.journal)
        if heading_parts is not None:
            _photos_step(
                "add_text (journal heading)",
                lambda: album.add_text(
                    heading_parts,
                    relative_position=PositionType.FIRST_IN_ALBUM,
                ),
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
                try:
                    path = self._media.prepare(
                        item, root=root, resolve=_safe_resolve(resolve_path, item)
                    )
                except FileNotFoundError:
                    raise
                except OSError as exc:
                    raise OSError(
                        f"Could not load photo '{item.id}' for Google Photos upload "
                        f"({item.relpath}): {exc}"
                    ) from exc
                prev = self._stamper.stamp_path(
                    path,
                    item,
                    index=absolute_index,
                    prev=prev,
                    album_day=album_day,
                    root=root,
                )
                done += 1
                try:
                    token = MediaItem.upload_media(gp, str(path))
                except Exception as exc:
                    raise RuntimeError(_format_upload_reject(item, path, exc)) from exc
                new_items.append(
                    NewMediaItem(item.caption, SimpleMediaItem(token, item.id))
                )
                if release is not None:
                    release(item.relpath)
                    play = (item.play_relpath or "").strip()
                    if play:
                        release(play)
                if sink is not None:
                    sink.emit("publish", item.relpath, current=done, total=total)
            if last_id is None:
                position = AlbumPosition(PositionType.LAST_IN_ALBUM)
            else:
                position = AlbumPosition(
                    PositionType.AFTER_MEDIA_ITEM,
                    relativeMediaItemId=last_id,
                )
            results = _photos_step(
                _batch_create_label(new_items),
                lambda: MediaItem.batchCreate(gp, new_items, album.id, position),
            )
            last_id = _last_created_media_id(results) or last_id
        return album


_ADD_TEXT_PART_LIMIT = 1000


def _safe_resolve(resolve_path: PathResolver, item: PreviewItem) -> PathResolver:
    """Wrap resolve so missing source paths keep the existing item-scoped message."""

    def resolve(relpath: str) -> Path:
        try:
            path = resolve_path(relpath)
        except FileNotFoundError as exc:
            missing = str(exc).strip() or relpath
            label = item.relpath if relpath == item.relpath else relpath
            raise FileNotFoundError(
                f"Could not load photo '{item.id}' for Google Photos upload "
                f"({label}). File missing from storage"
                + (f": {missing}" if missing != label else "")
                + "."
            ) from exc
        except OSError as exc:
            label = item.relpath if relpath == item.relpath else relpath
            raise OSError(
                f"Could not load photo '{item.id}' for Google Photos upload "
                f"({label}): {exc}"
            ) from exc
        return path

    return resolve


def _format_upload_reject(item: PreviewItem, upload_path: Path, exc: BaseException) -> str:
    """Human-readable Photos rejection; name source and bytes actually posted."""
    source = item.relpath
    if upload_path.name.lower() != Path(source).name.lower():
        where = f"source {source}; uploaded {upload_path.name}"
    else:
        where = source
    detail = str(exc).strip() or exc.__class__.__name__
    return f"Google Photos rejected upload of '{item.id}' ({where}): {detail}"


def _photos_step(label: str, action: Callable[[], object]) -> object:
    """Run a Photos API call; wrap failures with the step name for job.error."""
    try:
        return action()
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        raise RuntimeError(f"Google Photos {label} failed: {detail}") from exc


def _batch_create_label(new_items: Sequence[NewMediaItem]) -> str:
    ids: List[str] = []
    for entry in new_items:
        simple = getattr(entry, "simpleMediaItem", None) or getattr(
            entry, "simple_media_item", None
        )
        file_name = getattr(simple, "fileName", None) or getattr(simple, "file_name", None)
        if file_name:
            ids.append(str(file_name))
    if not ids:
        return f"batchCreate ({len(new_items)} items)"
    if len(ids) == 1:
        return f"batchCreate ('{ids[0]}')"
    return f"batchCreate ('{ids[0]}'…'{ids[-1]}', {len(ids)} items)"



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
