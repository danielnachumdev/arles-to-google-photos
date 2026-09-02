"""TDD tests for PreviewEditor: declarative, immutable album preview edits."""
from src.export.editor import PreviewEdits
from src.export.preview import AlbumJournal, AlbumPreview
from tests.support.suites import PreviewEditorSuite

import pytest


class TestPreviewEditor(PreviewEditorSuite):
    def test_change_title_and_description_only(self) -> None:
        item_a = self.item("a", "cap a")
        item_b = self.item("b", "cap b")
        preview = self.preview(item_a, item_b)

        result = self.apply(
            preview,
            PreviewEdits(title="New title", description="New description"),
        )

        assert result is not preview
        assert result.title == "New title"
        assert result.description == "New description"
        assert result.multi_index is False
        assert result.items == preview.items
        assert result.items[0] is item_a
        assert result.items[1] is item_b

    def test_change_one_caption_leaves_other_items_unchanged(self) -> None:
        item_a = self.item("a", "cap a")
        item_b = self.item("b", "cap b")
        preview = self.preview(item_a, item_b)

        result = self.apply(preview, PreviewEdits(captions={"a": "updated a"}))

        assert result.items[0].caption == "updated a"
        assert result.items[0].id == "a"
        assert result.items[0].relpath == item_a.relpath
        assert result.items[0].size_bytes == item_a.size_bytes
        assert result.items[1] is item_b
        assert result.items[1].caption == "cap b"
        assert result.title == preview.title
        assert result.description == preview.description

    def test_original_preview_unchanged_after_apply(self) -> None:
        item_a = self.item("a", "cap a")
        item_b = self.item("b", "cap b")
        preview = self.preview(item_a, item_b, title="Original", description="Keep me")
        original_items = preview.items

        result = self.apply(
            preview,
            PreviewEdits(
                title="Changed",
                description="Also changed",
                captions={"a": "new caption"},
            ),
        )

        assert result is not preview
        assert preview.title == "Original"
        assert preview.description == "Keep me"
        assert preview.items is original_items
        assert preview.items[0] is item_a
        assert preview.items[1] is item_b
        assert preview.items[0].caption == "cap a"
        assert preview.items[1].caption == "cap b"
        assert result.title == "Changed"
        assert result.description == "Also changed"
        assert result.items[0].caption == "new caption"
        assert result.items[1] is item_b

    def test_unknown_item_id_in_captions_raises_value_error(self) -> None:
        preview = self.preview(self.item("a"), self.item("b"))

        with pytest.raises(ValueError):
            self.apply(preview, PreviewEdits(captions={"missing": "nope"}))

    def test_replace_journal_leaves_items_unchanged(self) -> None:
        item_a = self.item("a", "cap a")
        original = AlbumJournal(heading="old", paragraphs=("p1",))
        preview = AlbumPreview(
            title="Album",
            description="Desc",
            multi_index=False,
            items=(item_a,),
            journal=original,
        )
        updated = AlbumJournal(heading="יומן", paragraphs=("new p",))

        result = self.apply(preview, PreviewEdits(journal=updated))

        assert result.journal == updated
        assert preview.journal is original
        assert result.items[0] is item_a
        assert result.title == "Album"
