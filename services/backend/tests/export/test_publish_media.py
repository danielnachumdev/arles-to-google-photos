"""TDD for PublishMediaPreparer (hydrate play sidecar / transcode before Photos)."""
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from src.export.preview import PreviewItem


def _video(
    item_id: str = "clip01",
    *,
    relpath: str = "hrimages/clip01hr.wmv",
    play: str | None = "preview/clip01.mp4",
    size: int = 9,
) -> PreviewItem:
    return PreviewItem(
        id=item_id,
        relpath=relpath,
        caption="",
        size_bytes=size,
        kind="video",
        play_relpath=play,
    )


class TestPublishMediaPreparer:
    def test_image_returns_resolved_source(self, tmp_path: Path) -> None:
        from src.export.publish_media import PublishMediaPreparer

        img = tmp_path / "hrimages" / "a.jpg"
        img.parent.mkdir(parents=True)
        img.write_bytes(b"jpeg")
        item = PreviewItem(
            id="a", relpath="hrimages/a.jpg", caption="", size_bytes=4, kind="image"
        )

        path = PublishMediaPreparer().prepare(
            item, root=tmp_path, resolve=lambda rel: tmp_path / rel
        )
        assert path == img

    def test_mp4_source_returns_resolved_source(self, tmp_path: Path) -> None:
        from src.export.publish_media import PublishMediaPreparer

        mp4 = tmp_path / "hrimages" / "clip01hr.mp4"
        mp4.parent.mkdir(parents=True)
        mp4.write_bytes(b"ftyp-real")
        item = _video(relpath="hrimages/clip01hr.mp4", play=None)

        path = PublishMediaPreparer().prepare(
            item, root=tmp_path, resolve=lambda rel: tmp_path / rel
        )
        assert path == mp4

    def test_hydrates_empty_play_placeholder_then_returns_companion(
        self, tmp_path: Path
    ) -> None:
        """Cloud Run sparse cache leaves 0-byte preview/*.mp4; must resolve real bytes."""
        from src.export.publish_media import PublishMediaPreparer

        wmv = tmp_path / "hrimages" / "clip01hr.wmv"
        play = tmp_path / "preview" / "clip01.mp4"
        wmv.parent.mkdir(parents=True)
        play.parent.mkdir(parents=True)
        wmv.write_bytes(b"wmv-bytes")
        play.write_bytes(b"")  # sparse placeholder
        durable_play = b"ftyp-real-preview-mp4"
        resolved: List[str] = []

        def resolve(rel: str) -> Path:
            resolved.append(rel)
            path = tmp_path / rel
            if rel == "preview/clip01.mp4":
                path.write_bytes(durable_play)
            return path

        path = PublishMediaPreparer().prepare(
            _video(), root=tmp_path, resolve=resolve
        )

        assert "preview/clip01.mp4" in resolved
        assert "hrimages/clip01hr.wmv" in resolved
        assert path.suffix.lower() == ".mp4"
        assert path.read_bytes() == durable_play
        assert path.stat().st_size > 0
        assert path != wmv

    def test_discards_empty_poison_companion_before_reuse(
        self, tmp_path: Path
    ) -> None:
        from src.export.publish_media import PublishMediaPreparer

        wmv = tmp_path / "hrimages" / "clip01hr.wmv"
        companion = tmp_path / "hrimages" / "clip01hr.mp4"
        play = tmp_path / "preview" / "clip01.mp4"
        wmv.parent.mkdir(parents=True)
        play.parent.mkdir(parents=True)
        wmv.write_bytes(b"wmv-bytes")
        companion.write_bytes(b"")  # leftover empty from prior failed publish
        play.write_bytes(b"ftyp-from-play")

        path = PublishMediaPreparer().prepare(
            _video(), root=tmp_path, resolve=lambda rel: tmp_path / rel
        )
        assert path == companion
        assert companion.read_bytes() == b"ftyp-from-play"

    def test_transcodes_when_no_play_sidecar(self, tmp_path: Path) -> None:
        from src.export.publish_media import PublishMediaPreparer

        wmv = tmp_path / "hrimages" / "clip01hr.wmv"
        wmv.parent.mkdir(parents=True)
        wmv.write_bytes(b"wmv-bytes")
        calls: List[tuple[Path, Path]] = []

        def fake_transcode(src: Path, dest: Path) -> bool:
            calls.append((src, dest))
            dest.write_bytes(b"ftyp-xcode")
            return True

        path = PublishMediaPreparer(transcode=fake_transcode).prepare(
            _video(play=None),
            root=tmp_path,
            resolve=lambda rel: tmp_path / rel,
        )
        assert calls == [(wmv, tmp_path / "hrimages" / "clip01hr.mp4")]
        assert path.read_bytes() == b"ftyp-xcode"

    def test_raises_clear_error_when_cannot_make_mp4(self, tmp_path: Path) -> None:
        from src.export.publish_media import PublishMediaPreparer

        wmv = tmp_path / "hrimages" / "clip01hr.wmv"
        wmv.parent.mkdir(parents=True)
        wmv.write_bytes(b"wmv-bytes")

        with pytest.raises(RuntimeError, match="clip01") as caught:
            PublishMediaPreparer(transcode=lambda *_a: False).prepare(
                _video(play=None),
                root=tmp_path,
                resolve=lambda rel: tmp_path / rel,
            )
        message = str(caught.value)
        assert "hrimages/clip01hr.wmv" in message
        assert "mp4" in message.lower()
