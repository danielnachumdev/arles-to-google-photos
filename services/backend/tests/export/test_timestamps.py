"""TDD: stamp capture times onto files so Google Photos shows date and gallery order."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.export.preview import PreviewItem
from tests.support.suites import TimestampSuite


class TestCaptureTimestampStamper(TimestampSuite):
    def test_stamp_module_exports_stamper(self) -> None:
        from src.export.timestamps import CaptureTimestampStamper

        assert CaptureTimestampStamper is not None

    def test_stamp_video_inherits_sibling_taken_on_and_gallery_order(self) -> None:
        """Videos without YYYYMMDD ids still share the album day and stay ordered."""
        photo = self.tmp_path / "hrimages" / "20120802_01hr.JPG"
        video = self.tmp_path / "hrimages" / "clip01hr.wmv"
        self.write_jpeg(photo)
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"WMV")

        self.stamper.stamp_upload(
            self.tmp_path,
            [
                self.item("20120802_01", "hrimages/20120802_01hr.JPG"),
                PreviewItem(
                    id="clip01",
                    relpath="hrimages/clip01hr.wmv",
                    caption="clip",
                    size_bytes=3,
                    taken_on=None,
                    kind="video",
                ),
            ],
        )

        expected_photo = datetime(2012, 8, 2, 0, 0, 0)
        expected_video = datetime(2012, 8, 2, 0, 0, 1)
        assert self.exif_original(photo) == expected_photo
        assert abs((self.mtime(video) - expected_video).total_seconds()) <= 2

    def test_stamp_video_between_exif_photos_keeps_increasing_order(self) -> None:
        """No taken_on on video: place it between sibling camera EXIF times."""
        first = self.tmp_path / "hrimages" / "a.jpg"
        video = self.tmp_path / "hrimages" / "midhr.wmv"
        second = self.tmp_path / "hrimages" / "b.jpg"
        first.parent.mkdir(parents=True, exist_ok=True)
        self.write_jpeg(first, datetime(2012, 8, 2, 10, 0, 0))
        video.write_bytes(b"WMV")
        self.write_jpeg(second, datetime(2012, 8, 2, 10, 0, 5))

        self.stamper.stamp_upload(
            self.tmp_path,
            [
                self.item("a", "hrimages/a.jpg", taken_on=None),
                PreviewItem(
                    id="mid",
                    relpath="hrimages/midhr.wmv",
                    caption="",
                    size_bytes=3,
                    taken_on=None,
                    kind="video",
                ),
                self.item("b", "hrimages/b.jpg", taken_on=None),
            ],
        )

        assert self.exif_original(first) == datetime(2012, 8, 2, 10, 0, 0)
        assert abs((self.mtime(video) - datetime(2012, 8, 2, 10, 0, 1)).total_seconds()) <= 2
        assert self.exif_original(second) == datetime(2012, 8, 2, 10, 0, 5)

    def test_stamp_mp4_embeds_creation_time_for_google_photos(self) -> None:
        """Library API reads container creation_time, not filesystem mtime."""
        path = self.tmp_path / "hrimages" / "clip01hr.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.write_mp4(path)

        self.stamper.stamp_upload(
            self.tmp_path,
            [
                PreviewItem(
                    id="clip01",
                    relpath="hrimages/clip01hr.mp4",
                    caption="",
                    size_bytes=path.stat().st_size,
                    taken_on=date(2012, 8, 2),
                    kind="video",
                ),
            ],
        )

        assert self.mp4_creation_time(path) == datetime(2012, 8, 2, 0, 0, 0)
        assert abs((self.mtime(path) - datetime(2012, 8, 2, 0, 0, 0)).total_seconds()) <= 2

    def test_stamp_wmv_stamps_companion_mp4_used_by_upload_transcode(self) -> None:
        """gp_wrapper uploads stem.mp4 when present; it must carry creation_time."""
        wmv = self.tmp_path / "hrimages" / "clip01hr.wmv"
        play = self.tmp_path / "preview" / "clip01.mp4"
        wmv.parent.mkdir(parents=True, exist_ok=True)
        play.parent.mkdir(parents=True, exist_ok=True)
        wmv.write_bytes(b"WMV-bytes")
        self.write_mp4(play)

        self.stamper.stamp_upload(
            self.tmp_path,
            [
                PreviewItem(
                    id="clip01",
                    relpath="hrimages/clip01hr.wmv",
                    caption="",
                    size_bytes=9,
                    taken_on=date(2012, 8, 2),
                    kind="video",
                    play_relpath="preview/clip01.mp4",
                ),
            ],
        )

        companion = self.tmp_path / "hrimages" / "clip01hr.mp4"
        assert companion.is_file()
        assert self.mp4_creation_time(companion) == datetime(2012, 8, 2, 0, 0, 0)
        assert abs((self.mtime(wmv) - datetime(2012, 8, 2, 0, 0, 0)).total_seconds()) <= 2

    def test_stamp_wmv_ignores_empty_play_placeholder(self) -> None:
        """Sparse 0-byte preview/*.mp4 must not become the upload companion."""
        wmv = self.tmp_path / "hrimages" / "clip01hr.wmv"
        play = self.tmp_path / "preview" / "clip01.mp4"
        wmv.parent.mkdir(parents=True, exist_ok=True)
        play.parent.mkdir(parents=True, exist_ok=True)
        self.write_wmv(wmv)
        play.write_bytes(b"")

        self.stamper.stamp_upload(
            self.tmp_path,
            [
                PreviewItem(
                    id="clip01",
                    relpath="hrimages/clip01hr.wmv",
                    caption="",
                    size_bytes=wmv.stat().st_size,
                    taken_on=date(2012, 8, 2),
                    kind="video",
                    play_relpath="preview/clip01.mp4",
                ),
            ],
        )

        companion = self.tmp_path / "hrimages" / "clip01hr.mp4"
        assert companion.is_file()
        assert companion.stat().st_size > 0
        assert self.mp4_creation_time(companion) == datetime(2012, 8, 2, 0, 0, 0)


    def test_stamp_wmv_without_play_sidecar_still_builds_upload_mp4(self) -> None:
        """gp_wrapper converts WMV→MP4 at upload; that file must exist with creation_time."""
        wmv = self.tmp_path / "hrimages" / "clip01hr.wmv"
        wmv.parent.mkdir(parents=True, exist_ok=True)
        # Real tiny WMV via ffmpeg so transcode has a decodeable source.
        self.write_wmv(wmv)

        self.stamper.stamp_upload(
            self.tmp_path,
            [
                PreviewItem(
                    id="clip01",
                    relpath="hrimages/clip01hr.wmv",
                    caption="",
                    size_bytes=wmv.stat().st_size,
                    taken_on=date(2012, 8, 2),
                    kind="video",
                ),
            ],
        )

        companion = self.tmp_path / "hrimages" / "clip01hr.mp4"
        assert companion.is_file()
        assert self.mp4_creation_time(companion) == datetime(2012, 8, 2, 0, 0, 0)

    def test_stamp_mov_builds_companion_mp4_not_only_source(self) -> None:
        """gp_wrapper also converts MOV→MP4; stamping only the .mov leaves today on Photos."""
        mov = self.tmp_path / "hrimages" / "clip01hr.MOV"
        mov.parent.mkdir(parents=True, exist_ok=True)
        self.write_mov(mov)

        self.stamper.stamp_upload(
            self.tmp_path,
            [
                PreviewItem(
                    id="clip01",
                    relpath="hrimages/clip01hr.MOV",
                    caption="",
                    size_bytes=mov.stat().st_size,
                    taken_on=date(2011, 4, 18),
                    kind="video",
                ),
            ],
        )

        companion = self.tmp_path / "hrimages" / "clip01hr.mp4"
        assert companion.is_file()
        assert self.mp4_creation_time(companion) == datetime(2011, 4, 18, 0, 0, 0)
        assert abs((self.mtime(mov) - datetime(2011, 4, 18, 0, 0, 0)).total_seconds()) <= 2

    def test_stamp_without_exif_uses_taken_on_plus_gallery_index(self) -> None:
        first = self.tmp_path / "hrimages" / "20120802_01hr.JPG"
        second = self.tmp_path / "hrimages" / "20120802_02hr.JPG"
        self.write_jpeg(first)
        self.write_jpeg(second)

        self.stamper.stamp_upload(
            self.tmp_path,
            [
                self.item("20120802_01", "hrimages/20120802_01hr.JPG"),
                self.item("20120802_02", "hrimages/20120802_02hr.JPG"),
            ],
        )

        expected_first = datetime(2012, 8, 2, 0, 0, 0)
        expected_second = datetime(2012, 8, 2, 0, 0, 1)
        assert self.exif_original(first) == expected_first
        assert self.exif_original(second) == expected_second
        assert abs((self.mtime(first) - expected_first).total_seconds()) <= 2
        assert abs((self.mtime(second) - expected_second).total_seconds()) <= 2

    def test_stamp_keeps_increasing_camera_exif(self) -> None:
        first = self.tmp_path / "a.jpg"
        second = self.tmp_path / "b.jpg"
        camera_first = datetime(2012, 8, 2, 2, 48, 34)
        camera_second = datetime(2012, 8, 2, 2, 50, 15)
        self.write_jpeg(first, camera_first)
        self.write_jpeg(second, camera_second)

        self.stamper.stamp_upload(
            self.tmp_path,
            [
                self.item("20120802_01", "a.jpg"),
                self.item("20120802_02", "b.jpg"),
            ],
        )

        assert self.exif_original(first) == camera_first
        assert self.exif_original(second) == camera_second
        assert abs((self.mtime(first) - camera_first).total_seconds()) <= 2
        assert abs((self.mtime(second) - camera_second).total_seconds()) <= 2

    def test_stamp_bumps_exif_so_gallery_order_stays_increasing(self) -> None:
        first = self.tmp_path / "later.jpg"
        second = self.tmp_path / "earlier.jpg"
        self.write_jpeg(first, datetime(2012, 8, 2, 6, 23, 38))
        self.write_jpeg(second, datetime(2012, 8, 2, 2, 48, 34))

        self.stamper.stamp_upload(
            self.tmp_path,
            [
                self.item("20120802_16", "later.jpg"),
                self.item("20120802_01", "earlier.jpg"),
            ],
        )

        assert self.exif_original(first) == datetime(2012, 8, 2, 6, 23, 38)
        assert self.exif_original(second) == datetime(2012, 8, 2, 6, 23, 39)

    def test_stamp_does_nothing_without_taken_on_or_exif(self) -> None:
        path = self.tmp_path / "plain.jpg"
        self.write_jpeg(path)
        before = path.stat().st_mtime

        self.stamper.stamp_upload(
            self.tmp_path,
            [self.item("plain", "plain.jpg", taken_on=None)],
        )

        assert self.exif_original(path) is None
        assert path.stat().st_mtime == before

    def test_stamp_ignores_missing_files(self) -> None:
        self.stamper.stamp_upload(
            self.tmp_path,
            [self.item("missing", "hrimages/missinghr.JPG")],
        )

    def test_stamp_non_jpeg_uses_taken_on_filetimes_only(self) -> None:
        path = self.tmp_path / "hrimages" / "clip01hr.wmv"
        path.parent.mkdir()
        path.write_bytes(b"WMV")
        self.stamper.stamp_upload(
            self.tmp_path,
            [self.item("clip01", "hrimages/clip01hr.wmv", taken_on=date(2012, 8, 2))],
        )
        assert abs((self.mtime(path) - datetime(2012, 8, 2, 0, 0, 0)).total_seconds()) <= 2

    def test_stamp_ignores_invalid_exif_datetime(self) -> None:
        from src.export.timestamps import _parse_exif_datetime

        assert _parse_exif_datetime(None) is None
        assert _parse_exif_datetime(b"not-a-date") is None
        path = self.tmp_path / "broken.jpg"
        self.write_jpeg(path)
        self.stamper.stamp_upload(
            self.tmp_path,
            [self.item("broken", "broken.jpg", taken_on=date(2012, 8, 2))],
        )
        assert self.exif_original(path) == datetime(2012, 8, 2, 0, 0, 0)
