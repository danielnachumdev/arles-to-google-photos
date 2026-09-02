"""Declarative, immutable edits for AlbumPreview (no Google Photos I/O)."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping, Optional

from .preview import AlbumJournal, AlbumPreview, PreviewItem


@dataclass(frozen=True)
class PreviewEdits:
    title: Optional[str] = None
    description: Optional[str] = None
    journal: Optional[AlbumJournal] = None
    captions: Mapping[str, str] = field(default_factory=dict)


class PreviewEditor:
    """Apply preview edits; always returns a new AlbumPreview."""

    @staticmethod
    def apply(preview: AlbumPreview, edits: PreviewEdits) -> AlbumPreview:
        known_ids = {item.id for item in preview.items}
        unknown_ids = set(edits.captions) - known_ids
        if unknown_ids:
            raise ValueError(
                "Unknown item id(s): " + ", ".join(sorted(unknown_ids))
            )

        new_items = tuple(
            _apply_item_edits(item, edits) for item in preview.items
        )
        return replace(
            preview,
            title=preview.title if edits.title is None else edits.title,
            description=(
                preview.description
                if edits.description is None
                else edits.description
            ),
            journal=preview.journal if edits.journal is None else edits.journal,
            items=new_items,
        )


def _apply_item_edits(item: PreviewItem, edits: PreviewEdits) -> PreviewItem:
    if item.id not in edits.captions:
        return item
    return replace(item, caption=edits.captions[item.id])
