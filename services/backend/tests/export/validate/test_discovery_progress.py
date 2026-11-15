"""Validate discovery emits sparse UI logs without sticky counters."""
from __future__ import annotations

from typing import Dict, Mapping

from src.export.scrape.client import FetchedResource
from src.export.validate.discovery import RemoteAlbumDiscovery
from tests.support.fakes.sinks import RecordingSink

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


def test_discovery_ui_logs_have_no_resetting_counters() -> None:
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
    sink = RecordingSink()
    albums, _warnings = RemoteAlbumDiscovery(_MapClient(pages)).discover(
        root, sink=sink
    )
    assert len(albums) == 2

    ui_messages = [message for _stage, message, _c, _t in sink.events]
    assert any("Fetching" in message and "gallery page" in message for message in ui_messages)
    assert any(message.startswith("Remote album ") for message in ui_messages)
    assert not any(message.startswith("Starting ") for message in ui_messages)
    # Milestone logs must not carry counters into the sticky channel.
    assert all(total == 0 for _stage, _message, _current, total in sink.events)
    assert sink.progress_events == []

    ops_messages = [message for _stage, message, _c, _t in sink.ops_events]
    assert any(message.startswith("Starting fetch ") for message in ops_messages)
    assert any(message.startswith("Starting remote item ") for message in ops_messages)
