"""TDD: Arles gallery scraper writes a parser-compatible local album tree."""
from __future__ import annotations

from pathlib import Path
from queue import Empty, Queue
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pytest

from src.export.parser import AlbumExportParser
from src.export.scrape.client import FetchedResource
from src.export.scrape.detect import GalleryItemRef
from src.export.scrape.models import ScrapeRequest
from src.export.scrape.scraper import (
    ArlesGalleryScraper,
    NotArlesGalleryError,
    ScrapeEmptyError,
    ScrapeFetchError,
    get_scraper,
    hr_output_filename,
    image_candidate_urls,
    poster_candidate_urls,
)
from src.jobs.events import JobEvent, JobEventBus, filter_events_by_audience
from tests.conftest import FIXTURES
from tests.support.fakes.http import FakeClock, FakeHttpClient
from tests.support.fakes.sinks import RecordingSink
from tests.support.suites import ArlesHttpScrapeSuite

HUB_INDEX = (FIXTURES / "arles_hub_index.html").read_text(encoding="utf-8")
WMV_LEAF_INDEX = (FIXTURES / "arles_embed_wmv" / "index.html").read_text(encoding="utf-8")
WMV_IMAGE_PAGE = (
    FIXTURES / "arles_embed_wmv" / "imagepages" / "0512_1_06[1].html"
).read_text(encoding="utf-8")
WMV_JPEG_PAGE = (
    FIXTURES / "arles_embed_wmv" / "imagepages" / "0512_1_05.html"
).read_text(encoding="utf-8")

HUB_CHILD_HREFS = (
    "Day1/index.html",
    "Day2/index.html",
    "Day3/index.html",
    "Day4/index.html",
    "Day5/index.html",
    "Day6/index.html",
    "Day7/index.html",
    "Day8/index.html",
)

TINY_JPEG = b"\xff\xd8\xff\xd9"
HR_JPEG = b"\xff\xd8" + b"HR" * 40 + b"\xff\xd9"
WEB_JPEG = b"\xff\xd8" + b"WEB" + b"\xff\xd9"

INDEX_HTML = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>2/8/2012 - Day1</title>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <link rel="stylesheet" TYPE="text/css" HREF="index.css">
</head>
<body>
  <!-- BeginTitle -->
  <table width="100%">
    <tr>
      <td align="center"><span class="gallerytitle">2/8/2012 - Day1</span></td>
    </tr>
    <tr>
      <td align="center"><span class="gallerydesc">A trip day</span></td>
    </tr>
  </table>
  <!-- EndTitle -->
  <table width="100%">
    <tr bgcolor="#FFFFFF">
      <td align="center"><a href="imagepages/20120802_01.html"><img
            src="thumbnails/TN_20120802_01.JPG" alt="20120802_01.JPG"></a></td>
      <td align="center"><a href="imagepages/20120802_02.html"><img
            src="thumbnails/TN_20120802_02.JPG" alt="20120802_02.JPG"></a></td>
    </tr>
  </table>
  <a href="../index.html">Home</a>
  <div class="WordSection1" dir="RTL">
    <p class="MsoNormal"><b>יומן</b></p>
    <p class="MsoNormal">היום יצאנו לטיול.</p>
    <p class="MsoNormal">היה יום נעים.</p>
  </div>
</body>
</html>
"""

INDEX_PAGE1 = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>Paged gallery</title>
  <link rel="stylesheet" TYPE="text/css" HREF="index.css">
</head>
<body>
  <!-- BeginTitle -->
  <span class="gallerytitle">Paged gallery</span>
  <!-- EndTitle -->
  <a href="imagepages/20120802_01.html"><img src="thumbnails/TN_20120802_01.JPG"></a>
  <a href="index2.html">Next</a>
</body>
</html>
"""

INDEX_PAGE2 = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>Paged gallery 2</title>
  <link rel="stylesheet" TYPE="text/css" HREF="index.css">
</head>
<body>
  <!-- BeginTitle -->
  <span class="gallerytitle">Paged gallery</span>
  <!-- EndTitle -->
  <a href="imagepages/20120802_02.html"><img src="thumbnails/TN_20120802_02.JPG"></a>
  <a href="index.html">Prev</a>
</body>
</html>
"""

INDEX_PAGE2_WITH_NEXT = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>Paged gallery 2</title>
  <link rel="stylesheet" TYPE="text/css" HREF="index.css">
</head>
<body>
  <!-- BeginTitle -->
  <span class="gallerytitle">1011_3</span>
  <!-- EndTitle -->
  <a href="imagepages/20111011_02.html"><img src="thumbnails/TN_20111011_02.JPG"></a>
  <a href="../index.html" target="_top">Home</a>
  <a href="index.html"><img src="res/prev.gif" alt="הקודם"></a>
  <a href="index3.html"><img src="res/next.gif" alt="הבא"></a>
</body>
</html>
"""

INDEX_PAGE3 = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>Paged gallery 3</title>
  <link rel="stylesheet" TYPE="text/css" HREF="index.css">
</head>
<body>
  <!-- BeginTitle -->
  <span class="gallerytitle">1011_3</span>
  <!-- EndTitle -->
  <a href="imagepages/20111011_03.html"><img src="thumbnails/TN_20111011_03.JPG"></a>
  <a href="index2.html"><img src="res/prev.gif" alt="Prev"></a>
</body>
</html>
"""

INDEX_PAGE1_NACHUM = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>1011_3</title>
  <link rel="stylesheet" TYPE="text/css" HREF="index.css">
</head>
<body>
  <!-- BeginTitle -->
  <span class="gallerytitle">1011_3</span>
  <!-- EndTitle -->
  <a href="imagepages/20111011_01.html"><img src="thumbnails/TN_20111011_01.JPG"></a>
  <div class="WordSection1" dir="RTL">
    <p class="MsoNormal"><b>יומן</b></p>
    <p class="MsoNormal">עמוד ראשון של האלבום.</p>
  </div>
  <a href="../index.html" target="_top">Home</a>
  <a href="index2.html"><img src="res/next.gif" alt="הבא"></a>
</body>
</html>
"""

IMAGE_PAGE_N1 = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html><head><title>01</title><link rel="stylesheet" TYPE="text/css" HREF="image.css"></head>
<body><div class="imagetitle">אחד</div>
<a href="20111011_02.html"><img src="../images/20111011_01.JPG"></a></body></html>
"""

IMAGE_PAGE_N2 = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html><head><title>02</title><link rel="stylesheet" TYPE="text/css" HREF="image.css"></head>
<body><div class="imagetitle">שניים</div>
<a href="20111011_03.html"><img src="../images/20111011_02.JPG"></a></body></html>
"""

IMAGE_PAGE_N3 = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html><head><title>03</title><link rel="stylesheet" TYPE="text/css" HREF="image.css"></head>
<body><div class="imagetitle">שלושה</div>
<img src="../images/20111011_03.JPG"></body></html>
"""

PARENT_INDEX = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>Trip 2012</title>
  <link rel="stylesheet" TYPE="text/css" HREF="index.css">
</head>
<body>
  <!-- BeginTitle -->
  <span class="gallerytitle">Trip 2012</span>
  <!-- EndTitle -->
  <a href="Day1/index.html"><img src="Day1/thumbnails/TN_01.JPG"></a>
  <a href="Day2/index.html"><img src="Day2/thumbnails/TN_02.JPG"></a>
  <a href="../index.html">Home</a>
</body>
</html>
"""

IMAGE_PAGE_01 = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>20120802_01.JPG</title>
  <script><!--
// Copyright 2001-2007 Digital Dutch (www.digitaldutch.com)
//--></script>
</head>
<body>
  <a href="20120802_02.html"><img src="../images/20120802_01.JPG" alt="20120802_01.JPG"></a>
  <div class="imagetitle">כיתוב ראשון</div>
</body>
</html>
"""

IMAGE_PAGE_02 = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head><title>20120802_02.JPG</title></head>
<body>
  <img src="../images/20120802_02.JPG" alt="20120802_02.JPG">
  <div class="imagetitle">כיתוב שני</div>
</body>
</html>
"""

IMAGE_PAGE_HR_SRC = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head><title>pic01.JPG</title></head>
<body>
  <img src="../hrimages/pic01hr.jpg" alt="pic01hr.jpg">
  <div class="imagetitle">hello</div>
</body>
</html>
"""

IMAGE_PAGE_NO_IMG = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head><title>20120802_01.JPG</title></head>
<body>
  <div class="imagetitle">caption only</div>
</body>
</html>
"""

TEXT_PAGE = """<!DOCTYPE html><html><body><div class="imagetitle">decoy</div></body></html>
"""

GALLERY_ARL = b"[Version]\nArlesVersionMajor=7\n"


def _leaf_pages(
    *,
    include_hr: bool = True,
    include_web: bool = True,
    include_decoy: bool = True,
    include_arl: bool = True,
) -> Dict[str, Tuple[int, bytes]]:
    base = "http://photos.example/2012/Day1"
    pages: Dict[str, Tuple[int, bytes]] = {
        f"{base}/index.html": (200, INDEX_HTML.encode("utf-8")),
        f"{base}/imagepages/20120802_01.html": (200, IMAGE_PAGE_01.encode("utf-8")),
        f"{base}/imagepages/20120802_02.html": (200, IMAGE_PAGE_02.encode("utf-8")),
        f"{base}/thumbnails/TN_20120802_01.JPG": (200, TINY_JPEG),
        f"{base}/thumbnails/TN_20120802_02.JPG": (200, TINY_JPEG),
    }
    if include_arl:
        pages[f"{base}/Gallery.arl"] = (200, GALLERY_ARL)
    if include_web:
        pages[f"{base}/images/20120802_01.JPG"] = (200, WEB_JPEG)
        pages[f"{base}/images/20120802_02.JPG"] = (200, WEB_JPEG)
    if include_hr:
        pages[f"{base}/hrimages/20120802_01hr.JPG"] = (200, HR_JPEG)
        pages[f"{base}/hrimages/20120802_02hr.JPG"] = (200, HR_JPEG)
    if include_decoy:
        pages[f"{base}/imagepages/Text.html"] = (200, TEXT_PAGE.encode("utf-8"))
        pages[f"{base}/images/Text.jpg"] = (200, b"DECOY")
        pages[f"{base}/hrimages/Text.jpg"] = (200, b"DECOY")
    return pages




















def _drain_job_events(bus: JobEventBus, job_id: str) -> List[JobEvent]:
    queue: Queue[JobEvent] = bus.subscribe(job_id)
    events: List[JobEvent] = []
    while True:
        try:
            events.append(queue.get_nowait())
        except Empty:
            break
    return events


























def _eta_index_html(item_ids: Sequence[str]) -> str:
    links = "\n".join(
        f'<a href="imagepages/{item_id}.html">'
        f'<img src="thumbnails/TN_{item_id}.JPG"></a>'
        for item_id in item_ids
    )
    return (
        "<!DOCTYPE html><html><head>"
        '<link rel="stylesheet" href="index.css"></head><body>'
        "<!-- BeginTitle -->"
        '<span class="gallerytitle">ETA album</span>'
        f"{links}</body></html>"
    )


def _eta_image_page(item_id: str, *, ext: str = ".JPG") -> str:
    return (
        "<!DOCTYPE html><html><body>"
        f'<img src="../hrimages/{item_id}hr{ext}" alt="{item_id}">'
        f'<div class="imagetitle">{item_id}</div>'
        "</body></html>"
    )


def _saved_events(sink: RecordingSink) -> List[Tuple[str, Optional[Dict[str, Any]]]]:
    paired: List[Tuple[str, Optional[Dict[str, Any]]]] = []
    for (_stage, message, _current, _total), extra in zip(sink.events, sink.extras):
        if message.startswith("Saved hrimages/"):
            paired.append((message, extra))
    return paired










def _wmv_embed_pages(video: bytes, poster: bytes, photo: bytes) -> Dict[str, Tuple[int, bytes]]:
    base = "https://albums.example/0512_1"
    return {
        f"{base}/index.html": (200, WMV_LEAF_INDEX.encode("utf-8")),
        f"{base}/Gallery.arl": (200, GALLERY_ARL),
        f"{base}/imagepages/0512_1_05.html": (200, WMV_JPEG_PAGE.encode("utf-8")),
        f"{base}/imagepages/0512_1_06[1].html": (200, WMV_IMAGE_PAGE.encode("utf-8")),
        f"{base}/imagepages/0512_1_06.wmv": (200, video),
        f"{base}/images/0512_1_05.JPG": (200, photo),
        f"{base}/images/0512_1_06[1].jpg": (200, poster),
        f"{base}/images/0512_1_06.JPG": (200, photo),
        f"{base}/thumbnails/TN_0512_1_05.JPG": (200, TINY_JPEG),
        f"{base}/thumbnails/TN_0512_1_06[1].jpg": (200, TINY_JPEG),
        f"{base}/hrimages/0512_1_05hr.JPG": (200, photo),
    }

class TestArlesGalleryScraper(ArlesHttpScrapeSuite):
    def test_scrape_emits_per_resource_download_progress(self, tmp_path: Path) -> None:
        client = FakeHttpClient(_leaf_pages(include_decoy=False))
        sink = RecordingSink()
        ArlesGalleryScraper(client=client).scrape(
            ScrapeRequest(url="http://photos.example/2012/Day1/index.html"),
            tmp_path,
            sink=sink,
        )

        assert sink.events
        assert all(stage == "scrape" for stage, _message, _current, _total in sink.events)
        messages = [message for _stage, message, _current, _total in sink.events]
        blob = " ".join(messages)
        assert any("Fetching gallery index" in message for message in messages)
        assert any("Downloading album" in message and "photos" in message for message in messages)
        assert any(message.startswith("Saved hrimages/") for message in messages)
        assert "20120802_01" in blob
        assert "20120802_02" in blob
        assert not any("Fetching image page" in message for message in messages)
        assert not any("Downloading hr image" in message for message in messages)
        ops_messages = [message for _stage, message, _current, _total in sink.ops_events]
        assert any("Fetching image page" in message for message in ops_messages)
        assert any("Downloading hr image" in message for message in ops_messages)
        assert any(message.startswith("GET ") and "200" in message for message in ops_messages)
        assert any(total == 2 for _stage, _message, _current, total in sink.events)
        assert any(current == 1 for _stage, _message, current, _total in sink.events)
        assert any(current == 2 for _stage, _message, current, _total in sink.events)

    def test_scrape_pagination_emits_index_page_progress(self, tmp_path: Path) -> None:
        base = "http://photos.example/paged"
        pages = {
            f"{base}/index.html": (200, INDEX_PAGE1.encode("utf-8")),
            f"{base}/index2.html": (200, INDEX_PAGE2.encode("utf-8")),
            f"{base}/imagepages/20120802_01.html": (200, IMAGE_PAGE_01.encode("utf-8")),
            f"{base}/imagepages/20120802_02.html": (200, IMAGE_PAGE_02.encode("utf-8")),
            f"{base}/images/20120802_01.JPG": (200, WEB_JPEG),
            f"{base}/images/20120802_02.JPG": (200, WEB_JPEG),
            f"{base}/Gallery.arl": (200, GALLERY_ARL),
        }
        sink = RecordingSink()
        ArlesGalleryScraper(client=FakeHttpClient(pages)).scrape(
            ScrapeRequest(url=f"{base}/index.html"),
            tmp_path,
            sink=sink,
        )

        ui_blob = " ".join(message for _stage, message, _current, _total in sink.events)
        ops_blob = " ".join(message for _stage, message, _current, _total in sink.ops_events)
        assert "Fetching gallery index" in ui_blob
        assert "index2.html" not in ui_blob
        assert "Fetching index page" in ops_blob
        assert "index2.html" in ops_blob

    def test_scrape_leaf_writes_parser_compatible_tree(self, tmp_path: Path) -> None:
        client = FakeHttpClient(_leaf_pages())
        scraper = ArlesGalleryScraper(client=client)
        request = ScrapeRequest(
            url="http://photos.example/2012/Day1/index.html",
            headers={"Cookie": "sid=1", "Authorization": "Bearer tok"},
        )

        result = scraper.scrape(request, tmp_path)

        assert result.album_root == tmp_path
        assert result.gallery_title == "2/8/2012 - Day1"
        assert result.child_gallery_urls == ()
        preview = AlbumExportParser().parse(result.album_root)
        assert preview.title == "2/8/2012 - Day1"
        assert preview.description == "A trip day"
        assert preview.journal is not None
        assert preview.journal.heading == "יומן"
        assert preview.journal.paragraphs == (
            "היום יצאנו לטיול.",
            "היה יום נעים.",
        )
        assert [item.id for item in preview.items] == ["20120802_01", "20120802_02"]
        assert preview.items[0].caption == "כיתוב ראשון"
        assert preview.items[1].caption == "כיתוב שני"
        assert preview.items[0].relpath == "hrimages/20120802_01hr.JPG"
        assert preview.items[1].relpath == "hrimages/20120802_02hr.JPG"
        assert (tmp_path / "hrimages" / "20120802_01hr.JPG").read_bytes() == HR_JPEG
        assert not (tmp_path / "imagepages" / "Text.html").exists()
        assert not (tmp_path / "hrimages" / "Text.jpg").exists()

    def test_scrape_prefers_hrimages_over_web_images(self, tmp_path: Path) -> None:
        client = FakeHttpClient(_leaf_pages(include_hr=True, include_web=True))
        result = ArlesGalleryScraper(client=client).scrape(
            ScrapeRequest(url="http://photos.example/2012/Day1/index.html"),
            tmp_path,
        )

        saved = (result.album_root / "hrimages" / "20120802_01hr.JPG").read_bytes()
        assert saved == HR_JPEG
        assert saved != WEB_JPEG

    def test_scrape_images_only_uses_trailing_hr_convention(self, tmp_path: Path) -> None:
        client = FakeHttpClient(_leaf_pages(include_hr=False, include_web=True))
        result = ArlesGalleryScraper(client=client).scrape(
            ScrapeRequest(url="http://photos.example/2012/Day1/index.html"),
            tmp_path,
        )

        hr_path = result.album_root / "hrimages" / "20120802_01hr.JPG"
        assert hr_path.is_file()
        assert hr_path.read_bytes() == WEB_JPEG
        preview = AlbumExportParser().parse(result.album_root)
        assert preview.items[0].id == "20120802_01"
        assert preview.items[0].relpath == "hrimages/20120802_01hr.JPG"

    def test_scrape_keeps_existing_trailing_hr_stem(self, tmp_path: Path) -> None:
        base = "http://photos.example/album"
        index = """<!DOCTYPE html>
    <html><head><link rel="stylesheet" href="index.css"></head>
    <body><!-- BeginTitle -->
    <span class="gallerytitle">HR album</span>
    <a href="imagepages/pic01.html"><img src="thumbnails/TN_pic01.jpg"></a>
    </body></html>
    """
        pages = {
            f"{base}/index.html": (200, index.encode("utf-8")),
            f"{base}/imagepages/pic01.html": (200, IMAGE_PAGE_HR_SRC.encode("utf-8")),
            f"{base}/hrimages/pic01hr.jpg": (200, HR_JPEG),
            f"{base}/Gallery.arl": (200, GALLERY_ARL),
        }
        result = ArlesGalleryScraper(client=FakeHttpClient(pages)).scrape(
            ScrapeRequest(url=f"{base}/index.html"),
            tmp_path,
        )

        assert (result.album_root / "hrimages" / "pic01hr.jpg").read_bytes() == HR_JPEG
        preview = AlbumExportParser().parse(result.album_root)
        assert preview.items[0].id == "pic01"
        assert preview.items[0].relpath == "hrimages/pic01hr.jpg"
        assert preview.items[0].caption == "hello"

    def test_scrape_falls_back_when_image_page_has_no_img(self, tmp_path: Path) -> None:
        base = "http://photos.example/Day1"
        index = """<!DOCTYPE html>
    <html><body><!-- BeginTitle -->
    <span class="gallerytitle">Mini</span>
    <a href="imagepages/20120802_01.html"><img src="thumbnails/TN_20120802_01.JPG"></a>
    </body></html>
    """
        pages = {
            f"{base}/index.html": (200, index.encode("utf-8")),
            f"{base}/imagepages/20120802_01.html": (
                200,
                IMAGE_PAGE_NO_IMG.encode("utf-8"),
            ),
            f"{base}/hrimages/20120802_01hr.JPG": (200, HR_JPEG),
            f"{base}/Gallery.arl": (200, GALLERY_ARL),
        }
        result = ArlesGalleryScraper(client=FakeHttpClient(pages)).scrape(
            ScrapeRequest(url=f"{base}/index.html"),
            tmp_path,
        )

        preview = AlbumExportParser().parse(result.album_root)
        assert preview.items[0].id == "20120802_01"
        assert preview.items[0].caption == "caption only"
        assert (result.album_root / "hrimages" / "20120802_01hr.JPG").read_bytes() == HR_JPEG

    def test_scrape_applies_headers_to_every_fetch(self, tmp_path: Path) -> None:
        client = FakeHttpClient(_leaf_pages(include_decoy=False))
        extra = {"Cookie": "sid=xyz", "Authorization": "Bearer tok"}
        ArlesGalleryScraper(client=client).scrape(
            ScrapeRequest(
                url="http://photos.example/2012/Day1/index.html",
                headers=extra,
            ),
            tmp_path,
        )

        assert client.calls
        for _url, headers in client.calls:
            assert headers["Cookie"] == "sid=xyz"
            assert headers["Authorization"] == "Bearer tok"

    def test_scrape_hub_index_returns_child_urls_without_fetching_days(
        self,
        tmp_path: Path,
    ) -> None:
        base = "http://photos.example/2012/hub1"
        pages = {
            f"{base}/index.html": (200, HUB_INDEX.encode("utf-8")),
            f"{base}/Day1/index.html": (200, INDEX_HTML.encode("utf-8")),
            f"{base}/Day2/index.html": (200, INDEX_HTML.encode("utf-8")),
        }
        client = FakeHttpClient(pages)
        sink = RecordingSink()
        result = ArlesGalleryScraper(client=client).scrape(
            ScrapeRequest(url=f"{base}/index.html"),
            tmp_path,
            sink=sink,
        )

        assert result.child_gallery_urls == tuple(
            f"{base}/{href}" for href in HUB_CHILD_HREFS
        )
        assert len(result.child_gallery_urls) == 8
        assert (tmp_path / "index.html").is_file()
        assert not (tmp_path / "hrimages").exists()
        assert not (tmp_path / "imagepages").exists()
        fetched = [url for url, _headers in client.calls]
        assert fetched[0] == f"{base}/index.html"
        assert all("/Day" not in url for url in fetched)
        ui_blob = " ".join(message for _stage, message, _current, _total in sink.events)
        ops_blob = " ".join(message for _stage, message, _current, _total in sink.ops_events)
        assert "Album index: 8 child albums" in ui_blob
        assert f"{base}/Day1/index.html" not in ui_blob
        assert f"{base}/Day1/index.html" in ops_blob

    def test_scrape_default_history_is_quiet_ops_has_fetches(self, tmp_path: Path) -> None:
        bus = JobEventBus()
        sink = bus.sink_for("job-1")
        pages = _leaf_pages(include_decoy=False)
        start = "http://photos.example/2012/Day1/index.html?token=secret"
        pages[start] = pages["http://photos.example/2012/Day1/index.html"]
        ArlesGalleryScraper(client=FakeHttpClient(pages)).scrape(
            ScrapeRequest(url=start),
            tmp_path,
            sink=sink,
        )
        events = _drain_job_events(bus, "job-1")
        ui_messages = [event.message for event in filter_events_by_audience(events, "ui")]
        ops_messages = [event.message for event in filter_events_by_audience(events, "ops")]

        assert any("Fetching gallery index" in message for message in ui_messages)
        assert any(
            "Downloading album" in message and "photos" in message for message in ui_messages
        )
        assert any(message.startswith("Saved hrimages/") for message in ui_messages)
        assert not any("Fetching image page" in message for message in ui_messages)
        assert not any("Downloading hr image" in message for message in ui_messages)
        assert not any("token=" in message for message in ui_messages)
        assert not any("token=" in message for message in ops_messages)
        assert any("Fetching image page" in message for message in ops_messages)
        assert any("Downloading hr image" in message for message in ops_messages)
        assert any(
            message.startswith("GET ") and "200" in message for message in ops_messages
        )

    def test_scrape_hub_default_history_summarizes_children(self, tmp_path: Path) -> None:
        base = "http://photos.example/2012/hub1"
        pages = {
            f"{base}/index.html": (200, HUB_INDEX.encode("utf-8")),
            f"{base}/Day1/index.html": (200, INDEX_HTML.encode("utf-8")),
        }
        bus = JobEventBus()
        sink = bus.sink_for("hub-1")
        ArlesGalleryScraper(client=FakeHttpClient(pages)).scrape(
            ScrapeRequest(url=f"{base}/index.html"),
            tmp_path,
            sink=sink,
        )
        events = _drain_job_events(bus, "hub-1")
        ui_messages = [event.message for event in filter_events_by_audience(events, "ui")]
        ops_messages = [event.message for event in filter_events_by_audience(events, "ops")]

        assert any("Album index:" in message and "child albums" in message for message in ui_messages)
        assert not any("/Day1/" in message for message in ui_messages)
        assert any(f"{base}/Day1/index.html" in message for message in ops_messages)

    def test_scrape_parent_index_returns_child_urls_without_photos(self, tmp_path: Path) -> None:
        base = "http://photos.example/2012"
        pages = {
            f"{base}/index.html": (200, PARENT_INDEX.encode("utf-8")),
            f"{base}/Gallery.arl": (200, GALLERY_ARL),
            f"{base}/Day1/index.html": (200, INDEX_HTML.encode("utf-8")),
            f"{base}/Day2/index.html": (200, INDEX_HTML.encode("utf-8")),
        }
        client = FakeHttpClient(pages)
        result = ArlesGalleryScraper(client=client).scrape(
            ScrapeRequest(url=f"{base}/index.html"),
            tmp_path,
        )

        assert result.gallery_title == "Trip 2012"
        assert result.child_gallery_urls == (
            f"{base}/Day1/index.html",
            f"{base}/Day2/index.html",
        )
        assert (tmp_path / "index.html").is_file()
        assert "יומן" not in (tmp_path / "index.html").read_text(encoding="utf-8")
        assert not (tmp_path / "hrimages").exists()
        assert not (tmp_path / "imagepages").exists()
        child_fetches = [
            url for url, _headers in client.calls if "/Day1/" in url or "/Day2/" in url
        ]
        assert child_fetches == []

    def test_scrape_pagination_merges_index2_into_index_html(self, tmp_path: Path) -> None:
        base = "http://photos.example/paged"
        pages = {
            f"{base}/index.html": (200, INDEX_PAGE1.encode("utf-8")),
            f"{base}/index2.html": (200, INDEX_PAGE2.encode("utf-8")),
            f"{base}/imagepages/20120802_01.html": (200, IMAGE_PAGE_01.encode("utf-8")),
            f"{base}/imagepages/20120802_02.html": (200, IMAGE_PAGE_02.encode("utf-8")),
            f"{base}/images/20120802_01.JPG": (200, WEB_JPEG),
            f"{base}/images/20120802_02.JPG": (200, WEB_JPEG),
            f"{base}/Gallery.arl": (200, GALLERY_ARL),
        }
        result = ArlesGalleryScraper(client=FakeHttpClient(pages)).scrape(
            ScrapeRequest(url=f"{base}/index.html"),
            tmp_path,
        )

        assert not (tmp_path / "index2.html").exists()
        preview = AlbumExportParser().parse(result.album_root)
        assert preview.multi_index is False
        assert [item.id for item in preview.items] == ["20120802_01", "20120802_02"]

    def test_scrape_starting_at_index2_merges_siblings_in_gallery_order(
        self, tmp_path: Path
    ) -> None:
        """Scrape index2.html still discovers index.html + index3.html."""
        base = "https://albums.example/album/2011/1011_3"
        pages = {
            f"{base}/index.html": (200, INDEX_PAGE1_NACHUM.encode("utf-8")),
            f"{base}/index2.html": (200, INDEX_PAGE2_WITH_NEXT.encode("utf-8")),
            f"{base}/index3.html": (200, INDEX_PAGE3.encode("utf-8")),
            f"{base}/imagepages/20111011_01.html": (200, IMAGE_PAGE_N1.encode("utf-8")),
            f"{base}/imagepages/20111011_02.html": (200, IMAGE_PAGE_N2.encode("utf-8")),
            f"{base}/imagepages/20111011_03.html": (200, IMAGE_PAGE_N3.encode("utf-8")),
            f"{base}/images/20111011_01.JPG": (200, WEB_JPEG),
            f"{base}/images/20111011_02.JPG": (200, WEB_JPEG),
            f"{base}/images/20111011_03.JPG": (200, WEB_JPEG),
            f"{base}/Gallery.arl": (200, GALLERY_ARL),
        }
        result = ArlesGalleryScraper(client=FakeHttpClient(pages)).scrape(
            ScrapeRequest(url=f"{base}/index2.html"),
            tmp_path,
        )

        assert not (tmp_path / "index2.html").exists()
        assert not (tmp_path / "index3.html").exists()
        saved = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert "יומן" in saved
        assert "עמוד ראשון של האלבום" in saved
        preview = AlbumExportParser().parse(result.album_root)
        assert preview.multi_index is False
        assert [item.id for item in preview.items] == [
            "20111011_01",
            "20111011_02",
            "20111011_03",
        ]

    def test_scrape_three_page_chain_from_index_html(self, tmp_path: Path) -> None:
        base = "https://albums.example/album/2011/1011_3"
        pages = {
            f"{base}/index.html": (200, INDEX_PAGE1_NACHUM.encode("utf-8")),
            f"{base}/index2.html": (200, INDEX_PAGE2_WITH_NEXT.encode("utf-8")),
            f"{base}/index3.html": (200, INDEX_PAGE3.encode("utf-8")),
            f"{base}/imagepages/20111011_01.html": (200, IMAGE_PAGE_N1.encode("utf-8")),
            f"{base}/imagepages/20111011_02.html": (200, IMAGE_PAGE_N2.encode("utf-8")),
            f"{base}/imagepages/20111011_03.html": (200, IMAGE_PAGE_N3.encode("utf-8")),
            f"{base}/images/20111011_01.JPG": (200, WEB_JPEG),
            f"{base}/images/20111011_02.JPG": (200, WEB_JPEG),
            f"{base}/images/20111011_03.JPG": (200, WEB_JPEG),
            f"{base}/Gallery.arl": (200, GALLERY_ARL),
        }
        result = ArlesGalleryScraper(client=FakeHttpClient(pages)).scrape(
            ScrapeRequest(url=f"{base}/index.html"),
            tmp_path,
        )

        preview = AlbumExportParser().parse(result.album_root)
        assert [item.id for item in preview.items] == [
            "20111011_01",
            "20111011_02",
            "20111011_03",
        ]

    def test_scrape_preserves_journal_bytes_in_index_html(self, tmp_path: Path) -> None:
        client = FakeHttpClient(_leaf_pages(include_decoy=False))
        result = ArlesGalleryScraper(client=client).scrape(
            ScrapeRequest(url="http://photos.example/2012/Day1/index.html"),
            tmp_path,
        )

        saved = (result.album_root / "index.html").read_bytes()
        assert b'class="WordSection1"' in saved
        assert "יומן".encode("utf-8") in saved
        assert b"BeginTitle" in saved

    def test_scrape_rejects_non_arles_page(self, tmp_path: Path) -> None:
        pages = {
            "http://example.com/blog.html": (
                200,
                b"<!DOCTYPE html><html><body><p>hello</p></body></html>",
            ),
        }
        with pytest.raises(NotArlesGalleryError) as excinfo:
            ArlesGalleryScraper(client=FakeHttpClient(pages)).scrape(
                ScrapeRequest(url="http://example.com/blog.html"),
                tmp_path,
            )
        assert excinfo.value.error_code == "not_arles"
        assert excinfo.value.url == "http://example.com/blog.html"
        assert "supported Arles" in str(excinfo.value)

    def test_scrape_year_toc_returns_child_gallery_urls(self, tmp_path: Path) -> None:
        html = (
            b"<!DOCTYPE html><html><head><title>2012 albums</title></head>"
            b"<body><h1>2012</h1>"
            b'<p><a href="2012/1212_1/index.html">December trip 1</a></p>'
            b'<p><a href="2012/1212_2/index.html">December trip 2</a></p>'
            b"</body></html>"
        )
        url = "https://albums.example/album/index2012.html"
        pages = {url: (200, html)}
        result = ArlesGalleryScraper(client=FakeHttpClient(pages)).scrape(
            ScrapeRequest(url=url),
            tmp_path,
        )
        assert result.child_gallery_urls == (
            "https://albums.example/album/2012/1212_1/index.html",
            "https://albums.example/album/2012/1212_2/index.html",
        )

    def test_scrape_raises_when_index_missing(self, tmp_path: Path) -> None:
        with pytest.raises(ScrapeFetchError) as excinfo:
            ArlesGalleryScraper(client=FakeHttpClient({})).scrape(
                ScrapeRequest(url="http://photos.example/missing/index.html"),
                tmp_path,
            )
        assert excinfo.value.error_code == "fetch_failed"
        assert excinfo.value.status_code == 404

    def test_scrape_raises_fetch_error_on_http_401(self, tmp_path: Path) -> None:
        url = "https://albums.example/private/index.html"
        pages = {url: (401, b"auth required")}
        with pytest.raises(ScrapeFetchError) as excinfo:
            ArlesGalleryScraper(client=FakeHttpClient(pages)).scrape(
                ScrapeRequest(url=url),
                tmp_path,
            )
        assert excinfo.value.error_code == "fetch_failed"
        assert excinfo.value.status_code == 401
        assert "401" in str(excinfo.value)

    def test_scrape_empty_arles_leaf_raises_scrape_empty(self, tmp_path: Path) -> None:
        html = (
            b"<!DOCTYPE HTML><html><head><title>Empty</title>"
            b'<link rel="stylesheet" href="index.css"></head>'
            b"<body><!-- BeginTitle -->"
            b'<span class="gallerytitle">Empty day</span>'
            b"<!-- EndTitle --></body></html>"
        )
        url = "https://albums.example/empty/index.html"
        pages = {url: (200, html)}
        with pytest.raises(ScrapeEmptyError) as excinfo:
            ArlesGalleryScraper(client=FakeHttpClient(pages)).scrape(
                ScrapeRequest(url=url),
                tmp_path,
            )
        assert excinfo.value.error_code == "scrape_empty"
        assert "No album photos" in str(excinfo.value)
        assert "leaf" in str(excinfo.value).lower() or "empty" in str(excinfo.value).lower()

    def test_get_scraper_emits_per_file_progress_plus_start_complete(
        self,
        tmp_path: Path,
    ) -> None:
        client = FakeHttpClient(_leaf_pages(include_decoy=False))
        sink = RecordingSink()
        get_scraper(client=client).scrape(
            "http://photos.example/2012/Day1/index.html",
            headers={"Cookie": "sid=1"},
            sink=sink,
        )

        messages = [message for _stage, message, _current, _total in sink.events]
        blob = " ".join(messages)
        assert any("Downloading album" in message and "photos" in message for message in messages)
        assert not any(message == "Download complete" for message in messages)
        assert not any(message == "Downloading album" for message in messages)
        ops_messages = [message for _stage, message, _current, _total in sink.ops_events]
        assert "Downloading album" in ops_messages
        assert "Download complete" in ops_messages
        assert "20120802_01" in blob
        assert "20120802_02" in blob
        assert any(total == 2 for _stage, _message, _current, total in sink.events)

    def test_wrapped_arles_scraper_forwards_sink(self, tmp_path: Path) -> None:
        from src.jobs.scraper import wrap_scraper

        client = FakeHttpClient(_leaf_pages(include_decoy=False))
        sink = RecordingSink()
        wrap_scraper(ArlesGalleryScraper(client=client)).scrape(
            "http://photos.example/2012/Day1/index.html",
            sink=sink,
            output_dir=tmp_path,
        )

        blob = " ".join(message for _stage, message, _current, _total in sink.events)
        assert "20120802_01" in blob
        assert "20120802_02" in blob
        assert any(total == 2 for _stage, _message, _current, total in sink.events)

    def test_get_scraper_leaf_is_jobs_compatible(self) -> None:
        from src.jobs.scraper import load_default_scraper, normalize_scrape_result

        client = FakeHttpClient(_leaf_pages(include_decoy=False))
        raw = get_scraper(client=client).scrape(
            "http://photos.example/2012/Day1/index.html",
            headers={"Cookie": "sid=1"},
        )
        result = normalize_scrape_result(raw)
        rels = {relpath for relpath, _data, _mtime in result.files}
        assert "index.html" in rels
        assert "hrimages/20120802_01hr.JPG" in rels
        assert "imagepages/20120802_01.html" in rels
        assert result.gallery_urls == ()
        assert any(
            call_headers.get("Cookie") == "sid=1" for _url, call_headers in client.calls
        )
        loaded = load_default_scraper()
        assert type(loaded).__name__ != "UnavailableAlbumScraper"

    def test_get_scraper_parent_returns_child_urls_without_preview_files(self) -> None:
        from src.jobs.scraper import normalize_scrape_result

        base = "http://photos.example/2012"
        pages = {
            f"{base}/index.html": (200, PARENT_INDEX.encode("utf-8")),
            f"{base}/Gallery.arl": (200, GALLERY_ARL),
        }
        raw = get_scraper(client=FakeHttpClient(pages)).scrape(f"{base}/index.html")
        result = normalize_scrape_result(raw)
        assert result.files == ()
        assert result.gallery_urls == (
            f"{base}/Day1/index.html",
            f"{base}/Day2/index.html",
        )

    def test_get_scraper_hub_returns_child_urls_without_preview_files(self) -> None:
        from src.jobs.scraper import normalize_scrape_result

        base = "http://photos.example/2012/hub1"
        pages = {f"{base}/index.html": (200, HUB_INDEX.encode("utf-8"))}
        raw = get_scraper(client=FakeHttpClient(pages)).scrape(f"{base}/index.html")
        result = normalize_scrape_result(raw)
        assert result.files == ()
        assert result.gallery_urls == tuple(f"{base}/{href}" for href in HUB_CHILD_HREFS)

    def test_scrape_saved_lines_include_size_and_eta_after_two_items(
        self,
        tmp_path: Path,
    ) -> None:
        base = "http://photos.example/eta"
        ids = ("pic01", "pic02", "pic03")
        jpeg = b"\xff\xd8" + b"A" * 50_000 + b"\xff\xd9"
        pages: Dict[str, Tuple[int, bytes]] = {
            f"{base}/index.html": (200, _eta_index_html(ids).encode("utf-8")),
            f"{base}/Gallery.arl": (200, GALLERY_ARL),
        }
        delays: Dict[str, float] = {}
        for item_id in ids:
            pages[f"{base}/imagepages/{item_id}.html"] = (
                200,
                _eta_image_page(item_id).encode("utf-8"),
            )
            hr_url = f"{base}/hrimages/{item_id}hr.JPG"
            pages[hr_url] = (200, jpeg)
            delays[hr_url] = 1.0
        clock = FakeClock()
        sink = RecordingSink()
        ArlesGalleryScraper(client=FakeHttpClient(pages, clock=clock, delays=delays), monotonic=clock).scrape(
            ScrapeRequest(url=f"{base}/index.html"),
            tmp_path,
            sink=sink,
        )

        saved = _saved_events(sink)
        assert len(saved) == 3
        first_message, first_extra = saved[0]
        assert "1/3" in first_message
        assert "KB" in first_message or "B" in first_message
        assert "left" not in first_message
        assert first_extra is not None
        assert first_extra["item_bytes"] == len(jpeg)
        assert "eta_seconds" not in first_extra
        assert any(current == 1 and total == 3 for _s, _m, current, total in sink.events)

        second_message, second_extra = saved[1]
        assert "2/3" in second_message
        assert "~1s left" in second_message
        assert second_extra is not None
        assert second_extra["eta_seconds"] == 1
        assert "bytes_done" in second_extra
        assert "rate_bps" in second_extra

        third_message, third_extra = saved[2]
        assert "3/3" in third_message
        assert "left" not in third_message
        assert third_extra is not None
        assert "eta_seconds" not in third_extra

    def test_scrape_video_item_is_labeled_and_does_not_inflate_eta(
        self,
        tmp_path: Path,
    ) -> None:
        base = "http://photos.example/mix"
        jpeg_ids = ("pic01", "pic02", "pic03")
        video_id = "clip01"
        jpeg = b"\xff\xd8" + b"J" * 80_000 + b"\xff\xd9"
        video = b"\x00\x00\x00\x18ftypmp42" + b"V" * (42 * 1024 * 1024)
        ids = jpeg_ids + (video_id, "pic04", "pic05")
        pages: Dict[str, Tuple[int, bytes]] = {
            f"{base}/index.html": (200, _eta_index_html(ids).encode("utf-8")),
            f"{base}/Gallery.arl": (200, GALLERY_ARL),
        }
        delays: Dict[str, float] = {}
        for item_id in jpeg_ids + ("pic04", "pic05"):
            pages[f"{base}/imagepages/{item_id}.html"] = (
                200,
                _eta_image_page(item_id).encode("utf-8"),
            )
            hr_url = f"{base}/hrimages/{item_id}hr.JPG"
            pages[hr_url] = (200, jpeg)
            delays[hr_url] = 1.0
        pages[f"{base}/imagepages/{video_id}.html"] = (
            200,
            _eta_image_page(video_id, ext=".mp4").encode("utf-8"),
        )
        video_url = f"{base}/hrimages/{video_id}hr.mp4"
        pages[video_url] = (200, video)
        delays[video_url] = 20.0

        clock = FakeClock()
        sink = RecordingSink()
        ArlesGalleryScraper(
            client=FakeHttpClient(pages, clock=clock, delays=delays),
            monotonic=clock,
        ).scrape(
            ScrapeRequest(url=f"{base}/index.html"),
            tmp_path,
            sink=sink,
        )

        saved = _saved_events(sink)
        assert len(saved) == 6
        video_message, video_extra = saved[3]
        assert "clip01hr.mp4" in video_message
        assert "video" in video_message
        assert "42 MB" in video_message or "42.0 MB" in video_message
        assert video_extra is not None
        assert video_extra["item_bytes"] == len(video)
        assert video_extra["eta_seconds"] == 2
        assert "~2s left" in video_message
        assert "MB remaining" not in video_message.lower()
        assert "40s" not in video_message
        assert "20s" not in video_message or "~2s left" in video_message

    def test_hr_output_filename_keeps_item_id_stem_and_source_video_ext(self) -> None:
        assert hr_output_filename("0512_1_06[1]", "0512_1_06.wmv") == "0512_1_06[1]hr.wmv"

    def test_image_candidate_urls_prefers_wmv_embed_over_poster_jpeg(self) -> None:
        item = GalleryItemRef(
            item_id="0512_1_06[1]",
            image_page_href="imagepages/0512_1_06[1].html",
            thumbnail_src="thumbnails/TN_0512_1_06[1].jpg",
        )
        candidates = image_candidate_urls(
            index_url="https://albums.example/0512_1/index.html",
            page_url="https://albums.example/0512_1/imagepages/0512_1_06[1].html",
            item=item,
            page_html=WMV_IMAGE_PAGE.encode("utf-8"),
        )

        assert candidates
        assert all(url.lower().endswith(".wmv") for url in candidates)
        assert "https://albums.example/0512_1/imagepages/0512_1_06.wmv" in candidates
        assert not any(url.lower().endswith((".jpg", ".jpeg")) for url in candidates)

    def test_poster_candidate_urls_prefer_images_jpeg_then_thumbnail(self) -> None:
        item = GalleryItemRef(
            item_id="0512_1_06[1]",
            image_page_href="imagepages/0512_1_06[1].html",
            thumbnail_src="thumbnails/TN_0512_1_06[1].jpg",
        )
        candidates = poster_candidate_urls(
            index_url="https://albums.example/0512_1/index.html",
            page_url="https://albums.example/0512_1/imagepages/0512_1_06[1].html",
            item=item,
            page_html=WMV_IMAGE_PAGE.encode("utf-8"),
        )

        assert candidates
        assert all(not url.lower().endswith(".wmv") for url in candidates)
        assert candidates[0] == "https://albums.example/0512_1/images/0512_1_06[1].jpg"
        assert "https://albums.example/0512_1/thumbnails/TN_0512_1_06[1].jpg" in candidates

    def test_scrape_arles_wmv_embed_downloads_video_and_poster(
        self,
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "src.export.video_preview.transcode_to_mp4",
            lambda source, dest: False,
        )
        poster = b"\xff\xd8" + b"P" * 10_000 + b"\xff\xd9"
        photo = b"\xff\xd8" + b"HR" * 80 + b"\xff\xd9"
        video = b"WMV" + b"V" * 50_000
        sink = RecordingSink()

        result = ArlesGalleryScraper(
            client=FakeHttpClient(_wmv_embed_pages(video, poster, photo))
        ).scrape(
            ScrapeRequest(url="https://albums.example/0512_1/index.html"),
            tmp_path,
            sink=sink,
        )

        hr_video = result.album_root / "hrimages" / "0512_1_06[1]hr.wmv"
        thumb = result.album_root / "thumbnails" / "TN_0512_1_06[1].jpg"
        assert hr_video.is_file()
        assert hr_video.read_bytes() == video
        assert thumb.is_file()
        assert thumb.read_bytes() == poster
        assert len(hr_video.read_bytes()) != len(poster)
        assert not (result.album_root / "preview" / "0512_1_06[1].mp4").is_file()
        preview = AlbumExportParser().parse(result.album_root)
        assert [item.id for item in preview.items] == ["0512_1_05", "0512_1_06[1]"]
        photo_item = preview.items[0]
        assert photo_item.kind == "image"
        assert photo_item.thumb_relpath is None
        video_item = preview.items[1]
        assert video_item.relpath == "hrimages/0512_1_06[1]hr.wmv"
        assert video_item.kind == "video"
        assert video_item.thumb_relpath == "thumbnails/TN_0512_1_06[1].jpg"
        assert video_item.play_relpath is None
        assert video_item.size_bytes == len(video)
        assert video_item.caption == ""
        saved = _saved_events(sink)
        assert any("0512_1_06[1]hr.wmv" in message and "video" in message for message, _extra in saved)

    def test_scrape_arles_wmv_embed_writes_preview_mp4_when_transcode_works(
        self,
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_transcode(source: Path, dest: Path) -> bool:
            dest = Path(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"ftyp-fake-mp4")
            return True

        monkeypatch.setattr("src.export.video_preview.transcode_to_mp4", fake_transcode)
        poster = b"\xff\xd8" + b"P" * 10_000 + b"\xff\xd9"
        photo = b"\xff\xd8" + b"HR" * 80 + b"\xff\xd9"
        video = b"WMV" + b"V" * 50_000

        result = ArlesGalleryScraper(
            client=FakeHttpClient(_wmv_embed_pages(video, poster, photo))
        ).scrape(
            ScrapeRequest(url="https://albums.example/0512_1/index.html"),
            tmp_path,
        )

        play = result.album_root / "preview" / "0512_1_06[1].mp4"
        assert play.is_file()
        assert play.read_bytes() == b"ftyp-fake-mp4"
        preview = AlbumExportParser().parse(result.album_root)
        video_item = preview.items[1]
        assert video_item.kind == "video"
        assert video_item.relpath == "hrimages/0512_1_06[1]hr.wmv"
        assert video_item.thumb_relpath == "thumbnails/TN_0512_1_06[1].jpg"
        assert video_item.play_relpath == "preview/0512_1_06[1].mp4"

