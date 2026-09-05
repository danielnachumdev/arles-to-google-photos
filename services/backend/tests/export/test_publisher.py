"""TDD for AlbumPublisher (mocked Google Photos)."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from gp_wrapper import PositionType

from src.export.preview import AlbumJournal, AlbumPreview, PreviewItem
from tests.support.suites import PublisherSuite


def _preview(
    *items: PreviewItem,
    title: str = "Mini",
    description: str | None = "Desc",
    journal: AlbumJournal | None = None,
) -> AlbumPreview:
    return AlbumPreview(
        title=title,
        description=description,
        multi_index=False,
        items=items,
        journal=journal,
    )


def _item(item_id: str, relpath: str, caption: str = "") -> PreviewItem:
    return PreviewItem(
        id=item_id,
        relpath=relpath,
        caption=caption,
        size_bytes=4,
    )










def _album_position(call) -> object:
    if len(call.args) > 3:
        return call.args[3]
    return call.kwargs.get("albumPosition")


def _add_text_parts(call) -> list:
    if call.args:
        return list(call.args[0])
    return list(call.kwargs["description_parts"])


def _add_text_position(call) -> object | None:
    if "relative_position" in call.kwargs:
        return call.kwargs["relative_position"]
    if len(call.args) > 1:
        return call.args[1]
    return None




def _publish_with_album(tmp_path: Path, preview: AlbumPreview):
    from src.export.publisher import AlbumPublisher

    img = tmp_path / "hrimages" / "a.jpg"
    img.parent.mkdir(exist_ok=True)
    if not img.exists():
        img.write_bytes(b"x")
    gp = MagicMock()
    album = MagicMock()
    album.id = "album-journal"
    album.productUrl = "https://photos.example/journal"
    with patch("src.export.publisher.Album") as AlbumCls, patch(
        "src.export.publisher.MediaItem"
    ) as MediaItemCls:
        AlbumCls.create.return_value = album
        MediaItemCls.upload_media.return_value = "tok"
        MediaItemCls.batchCreate.return_value = []
        AlbumPublisher().publish(gp, tmp_path, preview)
    return album, MediaItemCls

class TestAlbumPublisher(PublisherSuite):
    def test_publisher_module_exists(self) -> None:
        from src.export.publisher import AlbumPublisher  # noqa: F401

    def test_publish_creates_album_uploads_and_attaches(self, tmp_path: Path) -> None:
        from src.export.publisher import AlbumPublisher

        img = tmp_path / "hrimages" / "20120802_01hr.JPG"
        img.parent.mkdir()
        img.write_bytes(b"jpeg")

        preview = _preview(
            _item("20120802_01", "hrimages/20120802_01hr.JPG", "hello caption"),
        )
        gp = MagicMock(name="GooglePhotos")
        album = MagicMock(name="Album")
        album.id = "album-1"
        album.productUrl = "https://photos.example/album-1"

        sink = MagicMock()

        with patch("src.export.publisher.Album") as AlbumCls, patch(
            "src.export.publisher.MediaItem"
        ) as MediaItemCls:
            AlbumCls.create.return_value = album
            MediaItemCls.upload_media.return_value = "tok-1"
            MediaItemCls.batchCreate.return_value = []

            result = AlbumPublisher().publish(gp, tmp_path, preview, sink=sink)

        assert result is album
        AlbumCls.create.assert_called_once_with(gp, "Mini")
        album.add_text.assert_called_once_with(["Desc"])
        MediaItemCls.upload_media.assert_called_once_with(gp, str(img))
        MediaItemCls.batchCreate.assert_called_once()
        attached = MediaItemCls.batchCreate.call_args.args
        assert attached[0] is gp
        items = attached[1]
        assert len(items) == 1
        assert items[0].description == "hello caption"
        assert items[0].simpleMediaItem.fileName == "20120802_01"
        assert attached[2] == "album-1"
        position = attached[3]
        assert position.position == PositionType.LAST_IN_ALBUM
        sink.emit.assert_called()

    def test_publish_omits_description_when_none(self, tmp_path: Path) -> None:
        from src.export.publisher import AlbumPublisher

        img = tmp_path / "hrimages" / "a.jpg"
        img.parent.mkdir()
        img.write_bytes(b"x")
        preview = _preview(_item("a", "hrimages/a.jpg"), description=None)
        gp = MagicMock()
        album = MagicMock()
        album.id = "a3"
        album.productUrl = "https://photos.example/a3"

        with patch("src.export.publisher.Album") as AlbumCls, patch(
            "src.export.publisher.MediaItem"
        ) as MediaItemCls:
            AlbumCls.create.return_value = album
            MediaItemCls.upload_media.return_value = "t"
            MediaItemCls.batchCreate.return_value = []
            AlbumPublisher().publish(gp, tmp_path, preview)

        album.add_text.assert_not_called()

    def test_publish_stamps_capture_times_before_upload(self, tmp_path: Path) -> None:
        from src.export.publisher import AlbumPublisher

        first = tmp_path / "hrimages" / "20120802_01hr.JPG"
        second = tmp_path / "hrimages" / "20120802_02hr.JPG"
        first.parent.mkdir()
        first.write_bytes(b"jpeg")
        second.write_bytes(b"jpeg")

        preview = _preview(
            PreviewItem(
                id="20120802_01",
                relpath="hrimages/20120802_01hr.JPG",
                caption="one",
                size_bytes=4,
                taken_on=date(2012, 8, 2),
            ),
            PreviewItem(
                id="20120802_02",
                relpath="hrimages/20120802_02hr.JPG",
                caption="two",
                size_bytes=4,
                taken_on=date(2012, 8, 2),
            ),
        )
        stamper = MagicMock()
        gp = MagicMock()
        album = MagicMock()
        album.id = "a4"
        album.productUrl = "https://photos.example/a4"
        order: list[str] = []
        stamper.album_day_for.return_value = date(2012, 8, 2)
        stamper.stamp_path.side_effect = lambda *_a, **_k: (
            order.append("stamp") or date(2012, 8, 2)
        )

        with patch("src.export.publisher.Album") as AlbumCls, patch(
            "src.export.publisher.MediaItem"
        ) as MediaItemCls:
            AlbumCls.create.return_value = album
            MediaItemCls.upload_media.side_effect = lambda *_a, **_k: (
                order.append("upload") or "tok"
            )
            MediaItemCls.batchCreate.return_value = []
            AlbumPublisher(stamper=stamper).publish(gp, tmp_path, preview)

        assert stamper.album_day_for.called
        assert stamper.stamp_path.call_count == 2
        assert order == ["stamp", "upload", "stamp", "upload"]

    def test_publish_keeps_gallery_order_across_album_batches(self, tmp_path: Path) -> None:
        from src.export.publisher import AlbumPublisher

        folder = tmp_path / "hrimages"
        folder.mkdir()
        paths = []
        items = []
        for index in range(1, 4):
            relpath = f"hrimages/{index:02d}.jpg"
            path = tmp_path / relpath
            path.write_bytes(b"jpeg")
            paths.append(path)
            items.append(_item(f"id-{index:02d}", relpath, f"cap-{index}"))

        preview = _preview(*items)
        gp = MagicMock()
        album = MagicMock()
        album.id = "album-batches"
        album.productUrl = "https://photos.example/batches"
        stamper = MagicMock()

        first_ids = [MagicMock(mediaItem=MagicMock(id="mid-1")), MagicMock(mediaItem=MagicMock(id="mid-2"))]
        second_ids = [MagicMock(mediaItem=MagicMock(id="mid-3"))]
        order: list[str] = []

        with patch("src.export.publisher.MEDIA_ITEM_BATCH_CREATE_MAXIMUM_IDS", 2), patch(
            "src.export.publisher.Album"
        ) as AlbumCls, patch("src.export.publisher.MediaItem") as MediaItemCls:
            AlbumCls.create.return_value = album
            MediaItemCls.upload_media.side_effect = lambda *_a, **_k: (
                order.append("upload") or f"t{len(order)}"
            )
            MediaItemCls.batchCreate.side_effect = lambda *_a, **_k: (
                order.append("batch")
                or (first_ids if order.count("batch") == 1 else second_ids)
            )
            AlbumPublisher(stamper=stamper).publish(gp, tmp_path, preview)

        calls = MediaItemCls.batchCreate.call_args_list
        assert len(calls) == 2
        assert [item.simpleMediaItem.fileName for item in calls[0].args[1]] == ["id-01", "id-02"]
        assert [item.simpleMediaItem.fileName for item in calls[1].args[1]] == ["id-03"]
        first_pos = _album_position(calls[0])
        second_pos = _album_position(calls[1])
        assert first_pos.position == PositionType.LAST_IN_ALBUM
        assert second_pos.position == PositionType.AFTER_MEDIA_ITEM
        assert second_pos.relativeMediaItemId == "mid-2"
        # Attach after each upload batch (not after all uploads finish).
        assert order == ["upload", "upload", "batch", "upload", "batch"]

    def test_publish_attaches_first_batch_before_later_upload_failure(
        self,
        tmp_path: Path,
    ) -> None:
        """Interrupt mid-album must not leave a completely empty Photos album."""
        from src.export.publisher import AlbumPublisher

        folder = tmp_path / "hrimages"
        folder.mkdir()
        items = []
        for index in range(1, 4):
            relpath = f"hrimages/{index:02d}.jpg"
            (tmp_path / relpath).write_bytes(b"jpeg")
            items.append(_item(f"id-{index:02d}", relpath))

        preview = _preview(*items)
        gp = MagicMock()
        album = MagicMock()
        album.id = "album-partial"
        album.productUrl = "https://photos.example/partial"
        uploads = {"n": 0}

        def upload(_gp, _path, **_kw):
            uploads["n"] += 1
            if uploads["n"] >= 3:
                raise RuntimeError("simulated interrupt")
            return f"tok-{uploads['n']}"

        with patch("src.export.publisher.MEDIA_ITEM_BATCH_CREATE_MAXIMUM_IDS", 2), patch(
            "src.export.publisher.Album"
        ) as AlbumCls, patch("src.export.publisher.MediaItem") as MediaItemCls:
            AlbumCls.create.return_value = album
            MediaItemCls.upload_media.side_effect = upload
            MediaItemCls.batchCreate.return_value = [
                MagicMock(mediaItem=MagicMock(id="mid-1")),
                MagicMock(mediaItem=MagicMock(id="mid-2")),
            ]
            try:
                AlbumPublisher().publish(gp, tmp_path, preview)
                raise AssertionError("expected interrupt")
            except RuntimeError as exc:
                assert "simulated interrupt" in str(exc)

        MediaItemCls.batchCreate.assert_called_once()
        attached = MediaItemCls.batchCreate.call_args.args[1]
        assert [item.simpleMediaItem.fileName for item in attached] == [
            "id-01",
            "id-02",
        ]

    def test_publish_surfaces_masked_album_create_keyerror(self, tmp_path: Path) -> None:
        from src.export.publisher import AlbumPublisher

        img = tmp_path / "hrimages" / "a.jpg"
        img.parent.mkdir()
        img.write_bytes(b"x")
        preview = _preview(_item("a", "hrimages/a.jpg"), description=None)
        gp = MagicMock()

        with patch("src.export.publisher.Album") as AlbumCls:
            AlbumCls.create.side_effect = KeyError("id")
            try:
                AlbumPublisher().publish(gp, tmp_path, preview)
                raise AssertionError("expected RuntimeError")
            except RuntimeError as exc:
                assert "album create failed" in str(exc).lower()
                assert "missing album id" in str(exc).lower()

    def test_publish_journal_heading_and_paragraphs_are_separate_text_blocks(
        self,
        tmp_path: Path,
    ) -> None:
        journal = AlbumJournal(
            heading="יומן",
            paragraphs=("פסקה אחת", "פסקה שתיים"),
        )
        preview = _preview(
            _item("a", "hrimages/a.jpg"),
            description=None,
            journal=journal,
        )

        album, _media = _publish_with_album(tmp_path, preview)

        assert album.add_text.call_count == 2
        body_call, heading_call = album.add_text.call_args_list
        heading_parts = _add_text_parts(heading_call)
        body_parts = _add_text_parts(body_call)

        assert heading_parts == ["יומן"]
        assert "יומן" not in body_parts
        assert "פסקה אחת" in body_parts
        assert "פסקה שתיים" in body_parts
        assert "\n\n" in body_parts
        assert "".join(body_parts).index("פסקה אחת") < "".join(body_parts).index(
            "פסקה שתיים"
        )
        assert _add_text_position(body_call) == PositionType.FIRST_IN_ALBUM
        assert _add_text_position(heading_call) == PositionType.FIRST_IN_ALBUM

    def test_publish_no_journal_does_not_add_journal_text(self, tmp_path: Path) -> None:
        preview = _preview(_item("a", "hrimages/a.jpg"), description="Desc", journal=None)

        album, _media = _publish_with_album(tmp_path, preview)

        album.add_text.assert_called_once_with(["Desc"])

    def test_publish_description_only_still_adds_gallery_text(self, tmp_path: Path) -> None:
        preview = _preview(_item("a", "hrimages/a.jpg"), description="Gallery desc")

        album, _media = _publish_with_album(tmp_path, preview)

        album.add_text.assert_called_once_with(["Gallery desc"])

    def test_publish_journal_heading_sits_above_body_and_gallery_description(
        self,
        tmp_path: Path,
    ) -> None:
        journal = AlbumJournal(heading="יומן", paragraphs=("יום ראשון",))
        preview = _preview(
            _item("a", "hrimages/a.jpg", "cap"),
            description="Gallery desc",
            journal=journal,
        )

        album, media = _publish_with_album(tmp_path, preview)

        # FIRST_IN_ALBUM inserts at the start, so later calls sit higher.
        assert album.add_text.call_count == 3
        desc_call, body_call, heading_call = album.add_text.call_args_list
        assert _add_text_parts(desc_call) == ["Gallery desc"]
        assert _add_text_parts(body_call) == ["יום ראשון"]
        assert _add_text_parts(heading_call) == ["יומן"]
        assert _add_text_position(body_call) == PositionType.FIRST_IN_ALBUM
        assert _add_text_position(heading_call) == PositionType.FIRST_IN_ALBUM

        media.batchCreate.assert_called_once()
        position = _album_position(media.batchCreate.call_args)
        assert position.position == PositionType.LAST_IN_ALBUM

    def test_publish_journal_heading_only(self, tmp_path: Path) -> None:
        journal = AlbumJournal(heading="  יומן  ", paragraphs=("", "  "))
        preview = _preview(
            _item("a", "hrimages/a.jpg"),
            description=None,
            journal=journal,
        )

        album, _media = _publish_with_album(tmp_path, preview)

        album.add_text.assert_called_once()
        call = album.add_text.call_args
        assert _add_text_parts(call) == ["יומן"]
        assert _add_text_position(call) == PositionType.FIRST_IN_ALBUM

    def test_publish_journal_body_only_has_no_fake_title(self, tmp_path: Path) -> None:
        journal = AlbumJournal(heading="   ", paragraphs=("יום ראשון", "יום שני"))
        preview = _preview(
            _item("a", "hrimages/a.jpg"),
            description=None,
            journal=journal,
        )

        album, _media = _publish_with_album(tmp_path, preview)

        album.add_text.assert_called_once()
        call = album.add_text.call_args
        parts = _add_text_parts(call)
        assert "יום ראשון" in parts
        assert "יום שני" in parts
        assert "\n\n" in parts
        assert _add_text_position(call) == PositionType.FIRST_IN_ALBUM

    def test_publish_journal_heading_over_1000_chars_is_split_into_parts(
        self,
        tmp_path: Path,
    ) -> None:
        heading = "H" * 1001
        journal = AlbumJournal(heading=heading, paragraphs=())
        preview = _preview(
            _item("a", "hrimages/a.jpg"),
            description=None,
            journal=journal,
        )

        album, _media = _publish_with_album(tmp_path, preview)

        album.add_text.assert_called_once()
        call = album.add_text.call_args
        parts = _add_text_parts(call)
        assert parts
        assert all(len(part) <= 1000 for part in parts)
        assert "".join(parts) == heading
        assert _add_text_position(call) == PositionType.FIRST_IN_ALBUM

    def test_publish_skips_empty_journal(self, tmp_path: Path) -> None:
        empties = (
            None,
            AlbumJournal(heading=None, paragraphs=()),
            AlbumJournal(heading="", paragraphs=()),
            AlbumJournal(heading="   ", paragraphs=()),
            AlbumJournal(heading="", paragraphs=("", "  ")),
        )
        for journal in empties:
            preview = _preview(
                _item("a", "hrimages/a.jpg"),
                description=None,
                journal=journal,
            )
            album, _media = _publish_with_album(tmp_path, preview)
            album.add_text.assert_not_called()

    def test_publish_missing_file_raises_clear_message(self, tmp_path: Path) -> None:
        from src.export.publisher import AlbumPublisher

        preview = _preview(_item("0809_2_19_01", "hrimages/0809_2_19_01hr.JPG"))
        gp = MagicMock()
        album = MagicMock()
        album.id = "album-x"
        with patch("src.export.publisher.Album") as AlbumCls, patch(
            "src.export.publisher.MediaItem"
        ):
            AlbumCls.create.return_value = album

            def missing(_rel: str) -> Path:
                raise FileNotFoundError("hrimages/0809_2_19_01hr.JPG")

            with pytest.raises(FileNotFoundError, match="Could not load photo") as caught:
                AlbumPublisher().publish(
                    gp,
                    tmp_path,
                    preview,
                    resolve=missing,
                )
        assert "0809_2_19_01" in str(caught.value)
        assert "hrimages/0809_2_19_01hr.JPG" in str(caught.value)

    def test_publish_api_reject_includes_source_and_uploaded_mp4(
        self, tmp_path: Path
    ) -> None:
        from src.export.publisher import AlbumPublisher

        wmv = tmp_path / "hrimages" / "0308_1_22hr.wmv"
        play = tmp_path / "preview" / "0308_1_22.mp4"
        wmv.parent.mkdir(parents=True, exist_ok=True)
        play.parent.mkdir(parents=True, exist_ok=True)
        wmv.write_bytes(b"wmv")
        play.write_bytes(b"ftyp-real")
        preview = _preview(
            PreviewItem(
                id="0308_1_22",
                relpath="hrimages/0308_1_22hr.wmv",
                caption="",
                size_bytes=3,
                kind="video",
                play_relpath="preview/0308_1_22.mp4",
            )
        )
        gp = MagicMock()
        album = MagicMock()
        album.id = "album-x"
        with patch("src.export.publisher.Album") as AlbumCls, patch(
            "src.export.publisher.MediaItem"
        ) as MediaItem:
            AlbumCls.create.return_value = album
            MediaItem.upload_media.side_effect = RuntimeError(
                "400 Client Error: Bad Request for url: "
                "https://photoslibrary.googleapis.com/v1/uploads"
            )
            with pytest.raises(RuntimeError, match="Google Photos rejected upload") as caught:
                AlbumPublisher().publish(gp, tmp_path, preview)
        message = str(caught.value)
        assert "0308_1_22" in message
        assert "0308_1_22hr.wmv" in message
        assert "uploaded 0308_1_22hr.mp4" in message
        uploaded_path = Path(MediaItem.upload_media.call_args.args[1])
        assert uploaded_path.suffix.lower() == ".mp4"
        assert uploaded_path.stat().st_size > 0

    def test_publish_wmv_with_empty_play_placeholder_uploads_hydrated_mp4(
        self, tmp_path: Path
    ) -> None:
        from src.export.publish_media import PublishMediaPreparer
        from src.export.publisher import AlbumPublisher

        wmv = tmp_path / "hrimages" / "clip01hr.wmv"
        play = tmp_path / "preview" / "clip01.mp4"
        wmv.parent.mkdir(parents=True)
        play.parent.mkdir(parents=True)
        wmv.write_bytes(b"wmv-bytes")
        play.write_bytes(b"")  # sparse placeholder
        durable = b"ftyp-hydrated"

        def resolve(rel: str) -> Path:
            path = tmp_path / rel
            if rel == "preview/clip01.mp4":
                path.write_bytes(durable)
            return path

        preview = _preview(
            PreviewItem(
                id="clip01",
                relpath="hrimages/clip01hr.wmv",
                caption="",
                size_bytes=9,
                kind="video",
                play_relpath="preview/clip01.mp4",
            )
        )
        gp = MagicMock()
        album = MagicMock()
        album.id = "album-wmv"
        with patch("src.export.publisher.Album") as AlbumCls, patch(
            "src.export.publisher.MediaItem"
        ) as MediaItem:
            AlbumCls.create.return_value = album
            MediaItem.upload_media.return_value = "tok-mp4"
            MediaItem.batchCreate.return_value = []
            AlbumPublisher(media=PublishMediaPreparer()).publish(
                gp, tmp_path, preview, resolve=resolve
            )
        uploaded = Path(MediaItem.upload_media.call_args.args[1])
        assert uploaded.name == "clip01hr.mp4"
        assert uploaded.read_bytes() == durable


