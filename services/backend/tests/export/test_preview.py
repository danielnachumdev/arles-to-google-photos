"""Contract tests for AlbumPreview / PreviewItem and the day1_mini fixture tree."""
from datetime import date, datetime

from src.export.preview import AlbumJournal, AlbumPreview, PreviewItem
from tests.support.suites import ParserSuite


class TestAlbumPreviewModels(ParserSuite):
    def test_day1_mini_layout(self) -> None:
        assert (self.day1_mini / "index.html").is_file()
        assert (self.day1_mini / "hrimages" / "20120802_01hr.JPG").is_file()
        assert (self.day1_mini / "imagepages" / "20120802_01.html").is_file()

    def test_preview_item_is_immutable(self) -> None:
        item = PreviewItem(
            id="20120802_01",
            relpath="hrimages/20120802_01hr.JPG",
            caption="hello",
            size_bytes=16,
            last_modified=datetime(2012, 8, 2, 12, 0, 0),
            taken_on=date(2012, 8, 2),
        )
        try:
            item.caption = "nope"  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("PreviewItem must be immutable")

    def test_album_preview_holds_items(self) -> None:
        item = PreviewItem(
            id="20120802_01",
            relpath="hrimages/20120802_01hr.JPG",
            caption="כיתוב ראשון",
            size_bytes=16,
            taken_on=date(2012, 8, 2),
        )
        preview = AlbumPreview(
            title="2/8/2012 - mini fixture",
            description="A tiny album used in unit tests",
            multi_index=False,
            items=(item,),
            journal=None,
        )
        assert preview.title.startswith("2/8/2012")
        assert len(preview.items) == 1
        assert preview.items[0].id == "20120802_01"
        assert preview.items[0].taken_on == date(2012, 8, 2)
        assert preview.journal is None

    def test_album_journal_is_immutable(self) -> None:
        journal = AlbumJournal(heading="יומן", paragraphs=("a", "b"))
        try:
            journal.heading = "nope"  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("AlbumJournal must be immutable")
