"""TDD: per-item scrape ETA is time-based, not fake remaining bytes."""
from __future__ import annotations

from src.export.scrape.eta import (
    format_bytes,
    format_eta,
    is_video_filename,
    saved_hr_message,
)
from tests.support.suites import EtaSuite


class TestScrapeEta(EtaSuite):
    def test_format_bytes_uses_readable_units(self) -> None:
        assert format_bytes(84) == "84 B"
        assert format_bytes(640 * 1024) == "640 KB"
        assert format_bytes(int(42.1 * 1024 * 1024)) == "42.1 MB"
        assert format_bytes(int(1.5 * 1024 * 1024 * 1024)) == "1.5 GB"

    def test_format_eta_never_claims_byte_remainder(self) -> None:
        assert format_eta(0) == "~1s left"
        assert format_eta(12) == "~12s left"
        assert format_eta(80) == "~1m 20s left"
        assert format_eta(120) == "~2m left"
        assert format_eta(3600) == "~1h left"
        assert format_eta(3660) == "~1h 1m left"
        assert "MB" not in format_eta(3600)
        assert "KB" not in format_eta(90)

    def test_is_video_filename_uses_extension(self) -> None:
        assert is_video_filename("clip01hr.mp4") is True
        assert is_video_filename("clip01hr.MOV") is True
        assert is_video_filename("0512_1_06[1]hr.wmv") is True
        assert is_video_filename("20120802_01hr.JPG") is False

    def test_tracker_omits_eta_before_two_completed_items(self) -> None:
        tracker = self.tracker()
        tracker.start_item(0.0)
        first = tracker.finish_item(
            now=1.5,
            item_bytes=800_000,
            completed=1,
            total=16,
            filename="20120802_01hr.JPG",
        )
        assert first.eta_seconds is None
        assert first.item_bytes == 800_000
        assert first.bytes_done == 800_000
        assert first.rate_bps is not None
        message = saved_hr_message("20120802_01hr.JPG", first)
        assert "1/16" in message
        assert "left" not in message
        assert "MB remaining" not in message.lower()
        extra = first.extra()
        assert "eta_seconds" not in extra
        assert extra["item_bytes"] == 800_000
        assert extra["bytes_done"] == 800_000

    def test_tracker_eta_after_two_samples_is_remaining_times_median(self) -> None:
        tracker = self.tracker()
        tracker.start_item(0.0)
        tracker.finish_item(
            now=1.0, item_bytes=1000, completed=1, total=10, filename="a.jpg"
        )
        tracker.start_item(1.0)
        second = tracker.finish_item(
            now=3.0, item_bytes=2000, completed=2, total=10, filename="b.jpg"
        )
        assert second.eta_seconds == 12.0
        message = saved_hr_message("b.jpg", second)
        assert "2/10" in message
        assert "~12s left" in message
        assert second.extra()["eta_seconds"] == 12

    def test_tracker_median_drops_video_outlier_so_remaining_are_not_huge(self) -> None:
        tracker = self.tracker()
        marks = (
            (0.0, 1.0, 80_000, "a.jpg"),
            (1.0, 2.0, 90_000, "b.jpg"),
            (2.0, 3.1, 85_000, "c.jpg"),
            (3.1, 23.1, 42 * 1024 * 1024, "clip01hr.mp4"),
        )
        snapshot = None
        for index, (start, end, size, name) in enumerate(marks, start=1):
            tracker.start_item(start)
            snapshot = tracker.finish_item(
                now=end,
                item_bytes=size,
                completed=index,
                total=6,
                filename=name,
            )
        assert snapshot is not None
        assert snapshot.is_video is True
        assert snapshot.item_bytes == 42 * 1024 * 1024
        message = saved_hr_message("clip01hr.mp4", snapshot)
        assert "video" in message
        assert "42.0 MB" in message or "42 MB" in message
        assert snapshot.eta_seconds is not None
        assert snapshot.eta_seconds == 2.0
        assert snapshot.extra()["eta_seconds"] == 2
        assert "MB remaining" not in message.lower()
        assert "210" not in message
        assert "~40s" not in message
        assert "~20s" not in message

    def test_saved_message_labels_video_without_assuming_rest_are_videos(self) -> None:
        tracker = self.tracker()
        tracker.start_item(0.0)
        tracker.finish_item(
            now=1.0, item_bytes=50_000, completed=1, total=4, filename="a.jpg"
        )
        tracker.start_item(1.0)
        snap = tracker.finish_item(
            now=21.0,
            item_bytes=48 * 1024 * 1024,
            completed=2,
            total=4,
            filename="clip01hr.mp4",
        )
        message = saved_hr_message("clip01hr.mp4", snap)
        assert "video" in message
        assert "2/4" in message
        assert snap.eta_seconds is not None
        assert snap.eta_seconds < 40
