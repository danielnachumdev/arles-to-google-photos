"""Hub year-index pages must enqueue children (not be rejected as non-Arles)."""
from __future__ import annotations

from typing import Dict, Mapping

from src.export.scrape.client import FetchedResource
from src.export.validate.discovery import RemoteAlbumDiscovery

_HUB_HTML = b"""<!DOCTYPE html><html><body>
<a href="2001/0401_1/index.html">Passover</a>
<a href="2001/0501_1/index.html">May</a>
</body></html>"""

_LEAF_HTML = b"""<!DOCTYPE html><html><head>
<link rel="stylesheet" href="index.css">
</head><body>
<span class="gallerytitle">7-Apr-2001: Passover night</span>
<a href="imagepages/0401_1_01.html"><img src="thumbnails/TN_0401_1_01.jpg"></a>
</body></html>"""

_IMAGE_PAGE = b"""<!DOCTYPE html><html><body>
<div class="imagetitle">candle</div>
<img src="../hrimages/0401_1_01hr.JPG">
</body></html>"""


class _MapClient:
    def __init__(self, pages: Dict[str, bytes]) -> None:
        self._pages = pages

    def get(self, url: str, headers: Mapping[str, str]) -> FetchedResource:
        body = self._pages.get(url)
        if body is None:
            return FetchedResource(url=url, status_code=404, headers={}, content=b"")
        return FetchedResource(
            url=url,
            status_code=200,
            headers={"content-length": str(len(body))},
            content=body,
        )

    def head(self, url: str, headers: Mapping[str, str]) -> FetchedResource:
        body = self._pages.get(url)
        if body is None:
            return FetchedResource(url=url, status_code=404, headers={}, content=b"")
        return FetchedResource(
            url=url,
            status_code=200,
            headers={"content-length": str(len(body))},
            content=b"",
        )


def test_hub_year_index_discovers_leaf_albums() -> None:
    root = "https://example.com/album/index2001.html"
    leaf = "https://example.com/album/2001/0401_1/index.html"
    leaf2 = "https://example.com/album/2001/0501_1/index.html"
    pages = {
        root: _HUB_HTML,
        leaf: _LEAF_HTML,
        leaf2: _LEAF_HTML.replace(
            b"7-Apr-2001: Passover night", b"May album"
        ),
        "https://example.com/album/2001/0401_1/imagepages/0401_1_01.html": _IMAGE_PAGE,
        "https://example.com/album/2001/0501_1/imagepages/0401_1_01.html": _IMAGE_PAGE,
        "https://example.com/album/2001/0401_1/hrimages/0401_1_01hr.JPG": b"JPEGDATA",
        "https://example.com/album/2001/0501_1/hrimages/0401_1_01hr.JPG": b"JPEGDATA",
    }
    albums, warnings = RemoteAlbumDiscovery(_MapClient(pages)).discover(root)
    titles = sorted(a.title for a in albums)
    assert "7-Apr-2001: Passover night" in titles
    assert "May album" in titles
    assert not any("Not an Arles gallery page" in w for w in warnings)
