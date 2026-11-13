"""Unit tests for remote vs Photos album compare."""
from __future__ import annotations

from src.export.validate.compare import compare_indexes
from src.export.validate.models import (
    PhotosAlbumSnapshot,
    PhotosItemSnapshot,
    RemoteAlbumSnapshot,
    RemoteItemSnapshot,
)
from src.export.validate.titles import assign_title_ids


def test_assign_title_ids_suffixes_collisions() -> None:
    ids, warnings = assign_title_ids(["Day 1", "Day 1", "Day 2"])
    assert ids == ["Day 1", "Day 1 #2", "Day 2"]
    assert warnings


def test_compare_identical_albums() -> None:
    remote = [
        RemoteAlbumSnapshot(
            title_id="Day 1",
            title="Day 1",
            url="https://example.com/day1/index.html",
            items=(
                RemoteItemSnapshot(
                    item_id="20120802_01", caption="A", byte_size=100
                ),
            ),
        )
    ]
    photos = [
        PhotosAlbumSnapshot(
            title_id="Day 1",
            title="Day 1",
            album_id="alb1",
            product_url="https://photos.google.com/alb1",
            items=(
                PhotosItemSnapshot(
                    item_id="20120802_01",
                    filename="20120802_01",
                    caption="A",
                    byte_size=100,
                ),
            ),
        )
    ]
    report = compare_indexes(
        root_url="https://example.com/", remote=remote, photos=photos
    )
    assert report.identical is True
    assert report.summary["matched"] == 1
    assert report.matched[0].identical is True


def test_compare_size_and_caption_mismatch() -> None:
    remote = [
        RemoteAlbumSnapshot(
            title_id="Day 1",
            title="Day 1",
            url="https://example.com/day1/",
            items=(
                RemoteItemSnapshot(
                    item_id="a", caption="old", byte_size=10
                ),
            ),
        )
    ]
    photos = [
        PhotosAlbumSnapshot(
            title_id="Day 1",
            title="Day 1",
            album_id="alb1",
            product_url="",
            items=(
                PhotosItemSnapshot(
                    item_id="a", filename="a.jpg", caption="new", byte_size=11
                ),
            ),
        )
    ]
    report = compare_indexes(
        root_url="https://example.com/", remote=remote, photos=photos
    )
    assert report.identical is False
    fields = {m.field for m in report.matched[0].mismatches}
    assert fields == {"caption", "size"}


def test_compare_only_remote_and_only_photos() -> None:
    remote = [
        RemoteAlbumSnapshot(
            title_id="Remote Only",
            title="Remote Only",
            url="https://example.com/r/",
            items=(),
        )
    ]
    photos = [
        PhotosAlbumSnapshot(
            title_id="Photos Only",
            title="Photos Only",
            album_id="p",
            product_url="",
            items=(),
        )
    ]
    report = compare_indexes(
        root_url="https://example.com/", remote=remote, photos=photos
    )
    assert report.identical is False
    assert len(report.only_remote) == 1
    assert len(report.only_photos) == 1
