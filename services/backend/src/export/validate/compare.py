"""Match remote vs Photos albums by title_id and diff item metadata/size."""
from __future__ import annotations

from typing import Dict, List, Sequence

from .models import (
    ItemMismatch,
    MatchedAlbumReport,
    PhotosAlbumSnapshot,
    PhotosItemSnapshot,
    RemoteAlbumSnapshot,
    RemoteItemSnapshot,
    SideAlbumRef,
    ValidationReport,
)


def compare_indexes(
    *,
    root_url: str,
    remote: Sequence[RemoteAlbumSnapshot],
    photos: Sequence[PhotosAlbumSnapshot],
    warnings: Sequence[str] | None = None,
) -> ValidationReport:
    remote_by_id: Dict[str, RemoteAlbumSnapshot] = {a.title_id: a for a in remote}
    photos_by_id: Dict[str, PhotosAlbumSnapshot] = {a.title_id: a for a in photos}
    matched_ids = sorted(set(remote_by_id) & set(photos_by_id))
    only_remote_ids = sorted(set(remote_by_id) - set(photos_by_id))
    only_photos_ids = sorted(set(photos_by_id) - set(remote_by_id))

    matched: List[MatchedAlbumReport] = []
    content_mismatches = 0
    for title_id in matched_ids:
        report = _compare_album(remote_by_id[title_id], photos_by_id[title_id])
        if not report.identical:
            content_mismatches += 1
        matched.append(report)

    only_remote = [
        SideAlbumRef(
            title_id=aid,
            title=remote_by_id[aid].title,
            item_count=len(remote_by_id[aid].items),
            url=remote_by_id[aid].url,
        )
        for aid in only_remote_ids
    ]
    only_photos = [
        SideAlbumRef(
            title_id=aid,
            title=photos_by_id[aid].title,
            item_count=len(photos_by_id[aid].items),
            album_id=photos_by_id[aid].album_id,
            product_url=photos_by_id[aid].product_url,
        )
        for aid in only_photos_ids
    ]

    identical = (
        not only_remote
        and not only_photos
        and content_mismatches == 0
        and bool(matched)
    ) or (not remote and not photos)

    return ValidationReport(
        root_url=root_url,
        identical=identical,
        summary={
            "remote_albums": len(remote),
            "photos_albums": len(photos),
            "matched": len(matched),
            "only_remote": len(only_remote),
            "only_photos": len(only_photos),
            "content_mismatches": content_mismatches,
        },
        warnings=list(warnings or ()),
        matched=matched,
        only_remote=only_remote,
        only_photos=only_photos,
    )


def _compare_album(
    remote: RemoteAlbumSnapshot,
    photos: PhotosAlbumSnapshot,
) -> MatchedAlbumReport:
    remote_items: Dict[str, RemoteItemSnapshot] = {
        item.item_id: item for item in remote.items if item.item_id
    }
    photos_items: Dict[str, PhotosItemSnapshot] = {}
    for item in photos.items:
        key = item.item_id or item.filename
        if key and key not in photos_items:
            photos_items[key] = item

    only_remote = sorted(set(remote_items) - set(photos_items))
    only_photos = sorted(set(photos_items) - set(remote_items))
    mismatches: List[ItemMismatch] = []
    for item_id in sorted(set(remote_items) & set(photos_items)):
        r = remote_items[item_id]
        p = photos_items[item_id]
        if (r.caption or "") != (p.caption or ""):
            mismatches.append(
                ItemMismatch(
                    item_id=item_id,
                    field="caption",
                    remote=r.caption,
                    photos=p.caption,
                )
            )
        if r.byte_size is None or p.byte_size is None:
            mismatches.append(
                ItemMismatch(
                    item_id=item_id,
                    field="size_unavailable",
                    remote=r.byte_size,
                    photos=p.byte_size,
                )
            )
        elif r.byte_size != p.byte_size:
            mismatches.append(
                ItemMismatch(
                    item_id=item_id,
                    field="size",
                    remote=r.byte_size,
                    photos=p.byte_size,
                )
            )

    identical = not only_remote and not only_photos and not mismatches
    return MatchedAlbumReport(
        title_id=remote.title_id,
        title=remote.title,
        remote_url=remote.url,
        photos_album_id=photos.album_id,
        photos_product_url=photos.product_url,
        identical=identical,
        only_remote_items=only_remote,
        only_photos_items=only_photos,
        mismatches=mismatches,
    )
