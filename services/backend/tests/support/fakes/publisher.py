"""AlbumPublisher double: MagicMock that returns a canned product URL."""
from __future__ import annotations

from unittest.mock import MagicMock


def fake_publisher(
    *,
    product_url: str = "https://photos.example/album-1",
) -> MagicMock:
    publisher = MagicMock()
    album = MagicMock()
    album.productUrl = product_url
    publisher.publish.return_value = album
    return publisher
