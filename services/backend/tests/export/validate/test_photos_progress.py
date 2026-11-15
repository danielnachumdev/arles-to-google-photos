"""Photos indexer emits ops start lines without sticky counters."""
from __future__ import annotations

from typing import Any, List

from src.export.validate.photos_index import PhotosAlbumIndexer
from src.export.work_lane import AdaptiveWorkLane
from tests.support.fakes.sinks import RecordingSink


class _FakeMedia:
    def __init__(self, filename: str, size: int) -> None:
        self.filename = filename
        self.description = "caption"
        self.id = f"id-{filename}"
        self._size = size

    def byte_size(self) -> int:
        return self._size


class _FakeMediaItem:
    @staticmethod
    def search_all(
        gp: Any, albumId: str = "", pageSize: int = 50
    ) -> List[_FakeMedia]:
        del gp, albumId, pageSize
        return [
            _FakeMedia("0401_1_01.jpg", 11),
            _FakeMedia("0401_1_02.jpg", 22),
            _FakeMedia("0401_1_03.jpg", 33),
        ]


class _FakeAlbum:
    id = "album-1"
    title = "7-Apr-2001: Passover night"


def test_photos_album_items_ops_without_sticky_progress() -> None:
    sink = RecordingSink()
    indexer = PhotosAlbumIndexer()
    with AdaptiveWorkLane(max_workers=2) as lane:
        items = indexer._album_items(
            gp=object(),
            album=_FakeAlbum(),
            MediaItem=_FakeMediaItem,
            sink=sink,
            warnings=[],
            lane=lane,
        )
    assert len(items) == 3

    assert all(total == 0 for _stage, _message, _current, total in sink.events)
    assert sink.progress_events == []

    ops_starts = [
        message
        for _stage, message, _c, _t in sink.ops_events
        if message.startswith("Starting Photos size probe ")
    ]
    assert len(ops_starts) == 3
