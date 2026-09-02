"""Backward-compatible re-export. Prefer ``tests.support.fakes``."""
from __future__ import annotations

from tests.support.album import AlbumTree
from tests.support.fakes.scraper import FakeAlbumScraper, mini_album_files

__all__ = ["FakeAlbumScraper", "mini_album_files", "AlbumTree"]
