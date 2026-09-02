"""Parser / scrape-detect / timestamps / publisher / video suites."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Tuple

import piexif
import pytest
from gp_wrapper.utils import FileTimeService

from src.export.editor import PreviewEditor, PreviewEdits
from src.export.parser import AlbumExportParser
from src.export.preview import AlbumPreview, PreviewItem
from src.export.scrape.detect import detect_arles_page
from src.export.scrape.models import ScrapeRequest
from src.export.scrape.scraper import ArlesGalleryScraper
from tests.conftest import DAY1_ARLES, DAY1_MINI, FIXTURES
from tests.support.builders import PreviewBuilder, PreviewItemBuilder
from tests.support.fakes.http import FakeClock, FakeHttpClient
from tests.support.fakes.sinks import RecordingSink
from tests.support.suites.tmp import TmpPathSuite

TINY_JPEG = b"\xff\xd8\xff\xd9"
HR_JPEG = b"\xff\xd8" + b"HR" * 40 + b"\xff\xd9"
WEB_JPEG = b"\xff\xd8" + b"WEB" + b"\xff\xd9"
GALLERY_ARL = b"[Version]\nArlesVersionMajor=7\n"

_MIN_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00"
    + bytes([8] * 64)
    + b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    b"\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x03"
    b"\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\xff\xd9"
)


class ParserSuite(TmpPathSuite):
    """AlbumExportParser + fixture album roots + RecordingSink."""

    day1_mini: Path = DAY1_MINI
    day1_arles: Path = DAY1_ARLES

    def setup_method(self) -> None:
        self.parser = AlbumExportParser()
        self.sink = RecordingSink()

    def parse(self, root: Path | None = None, **kwargs: Any) -> AlbumPreview:
        return self.parser.parse(root if root is not None else self.tmp_path, **kwargs)


class DetectSuite:
    """Arles page detection helpers (HTML constants live on subclasses)."""

    def detect(self, html: str | bytes, page_url: str, **kwargs: Any) -> Any:
        return detect_arles_page(html, page_url=page_url, **kwargs)


class ArlesHttpScrapeSuite(TmpPathSuite):
    """FakeHttpClient + ArlesGalleryScraper + RecordingSink."""

    hub_index: str = (FIXTURES / "arles_hub_index.html").read_text(encoding="utf-8")
    wmv_leaf_index: str = (
        FIXTURES / "arles_embed_wmv" / "index.html"
    ).read_text(encoding="utf-8")
    wmv_image_page: str = (
        FIXTURES / "arles_embed_wmv" / "imagepages" / "0512_1_06[1].html"
    ).read_text(encoding="utf-8")
    wmv_jpeg_page: str = (
        FIXTURES / "arles_embed_wmv" / "imagepages" / "0512_1_05.html"
    ).read_text(encoding="utf-8")

    def setup_method(self) -> None:
        self.sink = RecordingSink()
        self.clock = FakeClock()

    def make_client(
        self,
        pages: Dict[str, Tuple[int, bytes]],
        *,
        clock: FakeClock | None = None,
        delays: Dict[str, float] | None = None,
    ) -> FakeHttpClient:
        return FakeHttpClient(pages, clock=clock, delays=delays)

    def scrape(
        self,
        url: str,
        pages: Dict[str, Tuple[int, bytes]],
        *,
        headers: Dict[str, str] | None = None,
        sink: Any = None,
        clock: FakeClock | None = None,
        delays: Dict[str, float] | None = None,
        output_dir: Path | None = None,
    ) -> Any:
        client = self.make_client(pages, clock=clock, delays=delays)
        self.client = client
        scraper = ArlesGalleryScraper(
            client=client,
            monotonic=clock if clock is not None else None,
        )
        return scraper.scrape(
            ScrapeRequest(url=url, headers=headers or {}),
            output_dir if output_dir is not None else self.tmp_path,
            sink=sink if sink is not None else self.sink,
        )


class TimestampSuite(TmpPathSuite):
    """CaptureTimestampStamper + tiny JPEG helpers."""

    def setup_method(self) -> None:
        from src.export.timestamps import CaptureTimestampStamper

        self.stamper = CaptureTimestampStamper()

    def item(
        self,
        item_id: str,
        relpath: str,
        *,
        taken_on: date | None = date(2012, 8, 2),
    ) -> PreviewItem:
        return PreviewItem(
            id=item_id,
            relpath=relpath,
            caption=item_id,
            size_bytes=16,
            taken_on=taken_on,
        )

    def write_jpeg(self, path: Path, taken: datetime | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_MIN_JPEG)
        if taken is None:
            return
        encoded = taken.strftime("%Y:%m:%d %H:%M:%S").encode("ascii")
        exif = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        exif["0th"][piexif.ImageIFD.DateTime] = encoded
        exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = encoded
        exif["Exif"][piexif.ExifIFD.DateTimeDigitized] = encoded
        piexif.insert(piexif.dump(exif), str(path))

    def write_mp4(self, path: Path) -> None:
        """Write a tiny real MP4 via imageio-ffmpeg (bundled with moviepy)."""
        self._write_ffmpeg_media(path, "libx264", "mp4")

    def write_mov(self, path: Path) -> None:
        self._write_ffmpeg_media(path, "libx264", "mov")

    def write_wmv(self, path: Path) -> None:
        self._write_ffmpeg_media(path, "wmv2", "asf")

    def _write_ffmpeg_media(self, path: Path, vcodec: str, fmt: str) -> None:
        import subprocess

        import imageio_ffmpeg

        path.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=64x64:d=0.1",
                "-c:v",
                vcodec,
                "-pix_fmt",
                "yuv420p",
                "-f",
                fmt,
                str(path),
            ],
            check=True,
            capture_output=True,
        )

    def mp4_creation_time(self, path: Path) -> datetime | None:
        import subprocess

        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run(
            [ffmpeg, "-i", str(path), "-f", "ffmetadata", "-"],
            check=False,
            capture_output=True,
            text=True,
        )
        blob = f"{result.stdout}\n{result.stderr}"
        for line in blob.splitlines():
            if "creation_time" not in line:
                continue
            raw = line.split(":", 1)[-1].strip()
            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S",
            ):
                try:
                    return datetime.strptime(raw, fmt)
                except ValueError:
                    continue
        return None

    def exif_original(self, path: Path) -> datetime | None:
        try:
            raw = piexif.load(str(path)).get("Exif", {}).get(
                piexif.ExifIFD.DateTimeOriginal
            )
        except Exception:
            return None
        if not raw:
            return None
        text = raw.decode("ascii") if isinstance(raw, bytes) else str(raw)
        return datetime.strptime(text, "%Y:%m:%d %H:%M:%S")

    def mtime(self, path: Path) -> datetime:
        got = FileTimeService().get(str(path))
        assert got.modification is not None
        return got.modification.replace(microsecond=0)


class VideoPreviewSuite(TmpPathSuite):
    """Local video poster/mp4 sidecar tests."""

    @pytest.fixture(autouse=True)
    def _bind_hr(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.hr = tmp_path / "hrimages"


class PreviewEditorSuite:
    """PreviewEditor.apply helpers."""

    def item(self, item_id: str, caption: str = "caption") -> PreviewItem:
        return (
            PreviewItemBuilder()
            .with_id(item_id)
            .with_caption(caption)
            .with_last_modified(datetime(2012, 8, 2, 12, 0, 0))
            .with_taken_on(None)
            .build()
        )

    def preview(
        self,
        *items: PreviewItem,
        title: str = "Album",
        description: str = "Desc",
    ) -> AlbumPreview:
        return (
            PreviewBuilder()
            .with_title(title)
            .with_description(description)
            .no_journal()
            .with_items(*items)
            .build()
        )

    def apply(self, preview: AlbumPreview, edits: PreviewEdits) -> AlbumPreview:
        return PreviewEditor.apply(preview, edits)


class PublisherSuite(TmpPathSuite):
    """AlbumPublisher mock helpers."""

    def item(self, item_id: str, relpath: str, caption: str = "") -> PreviewItem:
        return PreviewItem(
            id=item_id,
            relpath=relpath,
            caption=caption,
            size_bytes=4,
        )

    def preview(
        self,
        *items: PreviewItem,
        title: str = "Mini",
        description: str | None = "Desc",
        journal: Any = None,
    ) -> AlbumPreview:
        return AlbumPreview(
            title=title,
            description=description,
            multi_index=False,
            items=items,
            journal=journal,
        )


class ProgressSuite:
    """RecordingSink for progress helper tests."""

    def setup_method(self) -> None:
        self.sink = RecordingSink()


class EtaSuite:
    """ItemEtaTracker helpers."""

    def tracker(self) -> Any:
        from src.export.scrape.eta import ItemEtaTracker

        return ItemEtaTracker()


class OAuthSecretsSuite(TmpPathSuite):
    """Write client_secrets.json + monkeypatch env for oauth loader tests."""

    monkeypatch: pytest.MonkeyPatch

    @pytest.fixture(autouse=True)
    def _bind_oauth(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp_path = tmp_path
        self.monkeypatch = monkeypatch

    def _clear_oauth_env(self) -> None:
        for name in (
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRETS",
            "GOOGLE_CLIENT_SECRETS_JSON",
        ):
            self.monkeypatch.delenv(name, raising=False)

    def write_secrets(self, payload: Any) -> Path:
        path = self.tmp_path / "client_secrets.json"
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")
        self._clear_oauth_env()
        self.monkeypatch.setenv("GOOGLE_CLIENT_SECRETS", str(path))
        return path

    def missing_secrets(self) -> None:
        self._clear_oauth_env()
        self.monkeypatch.setenv(
            "GOOGLE_CLIENT_SECRETS", str(self.tmp_path / "missing.json")
        )


class AlbumCompatSuite(ParserSuite, ArlesHttpScrapeSuite):
    """Declarative fixtures + success assertions for legacy/live album shapes.

    Red-phase TDD target: folder parse and scrape both accept these albums
    (except intentional non-photo stubs).
    """

    TINY_JPEG = TINY_JPEG
    BASE = "https://albums.example/album/sample"
    FLAT_HR_TITLE = "Sample Flat HR Album"
    FLAT_TN_TITLE = "Sample Flat TN Album"
    STUB_TITLE = "Sample Flash Stub"
    HEBREW_TITLE = "כותרת גלריה לדוגמה"
    HEBREW_TITLE_1255 = HEBREW_TITLE.encode("windows-1255")
    NESTED_VIDEO_TITLE = "Sample Nested Video Album"
    NESTED_VIDEO_IDS = ("clip_a", "clip_b", "clip_c")
    VIEWER_ITEM_ID = "clip_01"
    VIEWER_CAPTION = "Sample viewer caption"
    VIEWER_FOLDER = "viewer_day"
    HR_PAGE_ITEM_ID = "clip_03"
    HR_PAGE_CAPTION = "Sample trailing-hr page caption"
    HR_PAGE_TITLE = "Sample Trailing HR Pages Album"

    def setup_method(self) -> None:
        ParserSuite.setup_method(self)
        ArlesHttpScrapeSuite.setup_method(self)

    # --- given: local folder trees ---

    def given_flat_legacy_hr_suffix_album(self, *, stem: str = "img_001") -> Path:
        """Photos + ``*hr.jpg`` sit in the album root (no ``hrimages/``)."""
        root = self.tmp_path / "flat_hr"
        root.mkdir()
        (root / "index.html").write_text(
            f"""<HTML>
<HEAD><TITLE>{self.FLAT_HR_TITLE}</TITLE></HEAD>
<BODY bgcolor="#FFFFFF">
<a href="{stem}.jpg"><img src="TN_{stem}.JPG"></a>
</BODY></HTML>
""",
            encoding="ascii",
        )
        (root / f"{stem}.jpg").write_bytes(self.TINY_JPEG)
        (root / f"{stem}hr.jpg").write_bytes(self.TINY_JPEG)
        (root / f"TN_{stem}.JPG").write_bytes(self.TINY_JPEG)
        return root

    def given_flat_legacy_tn_suffix_album(self, *, stem: str = "img_002") -> Path:
        """Flat root with ``name.jpg`` + ``nametn.jpg`` (no trailing ``hr``)."""
        root = self.tmp_path / "flat_tn"
        root.mkdir()
        (root / "index.html").write_text(
            f"""<HTML>
<HEAD><TITLE>{self.FLAT_TN_TITLE}</TITLE></HEAD>
<BODY>
<a href="{stem}.jpg"><img src="{stem}tn.jpg"></a>
</BODY></HTML>
""",
            encoding="ascii",
        )
        (root / f"{stem}.jpg").write_bytes(self.TINY_JPEG)
        (root / f"{stem}tn.jpg").write_bytes(self.TINY_JPEG)
        return root

    def given_stub_flash_album(self) -> Path:
        """Non-photo stub (Flash + home icon), not an Arles grid."""
        root = self.tmp_path / "stub_flash"
        root.mkdir()
        (root / "index.html").write_text(
            f"""<HTML>
<HEAD><TITLE>{self.STUB_TITLE}</TITLE></HEAD>
<BODY>
<object data="gallery.swf"></object>
<a href="../index.html"><img src="home.gif"></a>
</BODY></HTML>
""",
            encoding="ascii",
        )
        (root / "gallery.swf").write_bytes(b"FWS")
        (root / "home.gif").write_bytes(b"GIF89a")
        return root

    def given_windows1255_standard_arles_album(
        self, *, item_id: str = "img_101"
    ) -> Path:
        """Modern ``hrimages/`` + ``imagepages/`` tree whose HTML is Windows-1255."""
        root = self.tmp_path / "win1255_arles"
        (root / "hrimages").mkdir(parents=True)
        (root / "imagepages").mkdir()
        (root / "thumbnails").mkdir()
        (root / "index.html").write_bytes(
            self.windows1255_standard_index_html(item_id=item_id)
        )
        (root / "imagepages" / f"{item_id}.html").write_bytes(
            self.windows1255_image_page_html(item_id=item_id)
        )
        (root / "hrimages" / f"{item_id}hr.jpg").write_bytes(self.TINY_JPEG)
        (root / "thumbnails" / f"TN_{item_id}.JPG").write_bytes(self.TINY_JPEG)
        return root

    def given_single_image_viewer_album(
        self,
        *,
        item_id: str | None = None,
        caption: str | None = None,
        folder: str | None = None,
    ) -> Path:
        """Digital Dutch single-image viewer (``image.css`` + ``img`` under ``images/``).

        The photo is wrapped in ``<a href="index.html">`` (not a media/imagepages
        grid). Caption lives on ``index.html`` ``div.imagetitle``.
        """
        stem = item_id or self.VIEWER_ITEM_ID
        caption_text = caption if caption is not None else self.VIEWER_CAPTION
        root = self.tmp_path / (folder or self.VIEWER_FOLDER)
        (root / "images").mkdir(parents=True)
        (root / "hrimages").mkdir()
        (root / "icons").mkdir()
        (root / "index.html").write_text(
            self.single_image_viewer_index_html(
                item_id=stem, caption=caption_text
            ),
            encoding="utf-8",
        )
        (root / "image.css").write_text("/* viewer */\n", encoding="ascii")
        (root / "Gallery.arl").write_bytes(GALLERY_ARL)
        (root / "images" / f"{stem}.jpg").write_bytes(self.TINY_JPEG)
        (root / "hrimages" / f"{stem}hr.JPG").write_bytes(self.TINY_JPEG)
        (root / "icons" / "home.gif").write_bytes(b"GIF89a")
        (root / f"{stem}.jpg").write_bytes(self.TINY_JPEG)
        return root

    def given_trailing_hr_imagepages_album(
        self,
        *,
        item_id: str | None = None,
        caption: str | None = None,
        title: str | None = None,
    ) -> Path:
        """Standard Arles tree whose ``imagepages/`` filenames keep a trailing ``hr``."""
        stem = item_id or self.HR_PAGE_ITEM_ID
        caption_text = caption if caption is not None else self.HR_PAGE_CAPTION
        gallery_title = title if title is not None else self.HR_PAGE_TITLE
        root = self.tmp_path / "trailing_hr_pages"
        (root / "hrimages").mkdir(parents=True)
        (root / "imagepages").mkdir()
        (root / "thumbnails").mkdir()
        (root / "index.html").write_text(
            f"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html><head>
  <title>{gallery_title}</title>
  <link rel="stylesheet" TYPE="text/css" HREF="index.css">
</head><body>
  <!-- BeginTitle -->
  <span class="gallerytitle">{gallery_title}</span>
  <!-- EndTitle -->
  <a href="imagepages/{stem}hr.html">
    <img src="thumbnails/TN_{stem}hr.jpg" alt="{stem}">
  </a>
</body></html>
""",
            encoding="utf-8",
        )
        (root / "imagepages" / f"{stem}hr.html").write_text(
            f"""<!DOCTYPE HTML><html><body>
<div class="imagetitle">{caption_text}</div>
<img src="../hrimages/{stem}hr.JPG">
</body></html>
""",
            encoding="utf-8",
        )
        (root / "hrimages" / f"{stem}hr.JPG").write_bytes(self.TINY_JPEG)
        (root / "thumbnails" / f"TN_{stem}hr.jpg").write_bytes(self.TINY_JPEG)
        (root / "Gallery.arl").write_bytes(GALLERY_ARL)
        return root

    # --- given: fake live HTTP surfaces ---

    def given_flat_legacy_hr_suffix_site(
        self, *, stem: str = "img_001"
    ) -> Dict[str, Tuple[int, bytes]]:
        html = f"""<HTML>
<HEAD><TITLE>{self.FLAT_HR_TITLE}</TITLE></HEAD>
<BODY bgcolor="#FFFFFF">
<a href="{stem}.jpg"><img src="TN_{stem}.JPG"></a>
</BODY></HTML>
""".encode("ascii")
        return {
            f"{self.BASE}/index.html": (200, html),
            f"{self.BASE}/{stem}.jpg": (200, self.TINY_JPEG),
            f"{self.BASE}/{stem}hr.jpg": (200, self.TINY_JPEG),
            f"{self.BASE}/TN_{stem}.JPG": (200, self.TINY_JPEG),
            f"{self.BASE}/Gallery.arl": (404, b""),
        }

    def given_flat_legacy_tn_suffix_site(
        self, *, stem: str = "img_002"
    ) -> Dict[str, Tuple[int, bytes]]:
        html = f"""<HTML>
<HEAD><TITLE>{self.FLAT_TN_TITLE}</TITLE></HEAD>
<BODY>
<a href="{stem}.jpg"><img src="{stem}tn.jpg"></a>
</BODY></HTML>
""".encode("ascii")
        return {
            f"{self.BASE}/index.html": (200, html),
            f"{self.BASE}/{stem}.jpg": (200, self.TINY_JPEG),
            f"{self.BASE}/{stem}tn.jpg": (200, self.TINY_JPEG),
            f"{self.BASE}/Gallery.arl": (404, b""),
        }

    def given_stub_flash_site(self) -> Dict[str, Tuple[int, bytes]]:
        html = f"""<HTML>
<HEAD><TITLE>{self.STUB_TITLE}</TITLE></HEAD>
<BODY>
<object data="gallery.swf"></object>
</BODY></HTML>
""".encode("ascii")
        return {f"{self.BASE}/index.html": (200, html)}

    def given_single_image_viewer_site(
        self,
        *,
        item_id: str | None = None,
        caption: str | None = None,
    ) -> Dict[str, Tuple[int, bytes]]:
        """Remote single-image viewer: content ``img`` only (no ``hrimages/`` on host)."""
        stem = item_id or self.VIEWER_ITEM_ID
        caption_text = caption if caption is not None else self.VIEWER_CAPTION
        html = self.single_image_viewer_index_html(
            item_id=stem, caption=caption_text
        ).encode("utf-8")
        return {
            f"{self.BASE}/index.html": (200, html),
            f"{self.BASE}/images/{stem}.jpg": (200, self.TINY_JPEG),
            f"{self.BASE}/{stem}.jpg": (200, self.TINY_JPEG),
            f"{self.BASE}/icons/home.gif": (200, b"GIF89a"),
            f"{self.BASE}/Gallery.arl": (200, GALLERY_ARL),
            f"{self.BASE}/image.css": (200, b"/* viewer */\n"),
        }

    def given_trailing_hr_imagepages_site(
        self,
        *,
        item_id: str | None = None,
        caption: str | None = None,
        title: str | None = None,
    ) -> Dict[str, Tuple[int, bytes]]:
        stem = item_id or self.HR_PAGE_ITEM_ID
        caption_text = caption if caption is not None else self.HR_PAGE_CAPTION
        gallery_title = title if title is not None else self.HR_PAGE_TITLE
        index = f"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html><head>
  <title>{gallery_title}</title>
  <link rel="stylesheet" TYPE="text/css" HREF="index.css">
</head><body>
  <!-- BeginTitle -->
  <span class="gallerytitle">{gallery_title}</span>
  <!-- EndTitle -->
  <a href="imagepages/{stem}hr.html">
    <img src="thumbnails/TN_{stem}hr.jpg">
  </a>
</body></html>
""".encode("utf-8")
        page = f"""<!DOCTYPE HTML><html><body>
<div class="imagetitle">{caption_text}</div>
<img src="../hrimages/{stem}hr.JPG">
</body></html>
""".encode("utf-8")
        return {
            f"{self.BASE}/index.html": (200, index),
            f"{self.BASE}/imagepages/{stem}hr.html": (200, page),
            f"{self.BASE}/hrimages/{stem}hr.JPG": (200, self.TINY_JPEG),
            f"{self.BASE}/thumbnails/TN_{stem}hr.jpg": (200, self.TINY_JPEG),
            f"{self.BASE}/Gallery.arl": (200, GALLERY_ARL),
        }

    def given_nested_video_gallery_site(
        self,
        *,
        ids: Tuple[str, ...] | None = None,
        title: str | None = None,
    ) -> Dict[str, Tuple[int, bytes]]:
        """Deep nested media links (any folder names) with full-size siblings."""
        item_ids = ids or self.NESTED_VIDEO_IDS
        gallery_title = title or self.NESTED_VIDEO_TITLE
        cells = []
        pages: Dict[str, Tuple[int, bytes]] = {}
        for item_id in item_ids:
            small = f"media/deep/preview/{item_id}_small_320x240_100Kbps.wmv"
            full = f"media/deep/preview/{item_id}_Big.wmv"
            cells.append(
                f'<a href="{small}"><img src="thumbnails/TN_{item_id}.jpg"></a>'
            )
            pages[f"{self.BASE}/{small}"] = (
                200,
                b"wmv-small-" + item_id.encode(),
            )
            pages[f"{self.BASE}/{full}"] = (
                200,
                b"wmv-full-" + item_id.encode() + b"-XXXX",
            )
            pages[f"{self.BASE}/stills/{item_id}.jpg"] = (200, self.TINY_JPEG)
            pages[f"{self.BASE}/thumbnails/TN_{item_id}.jpg"] = (200, self.TINY_JPEG)
        html = f"""<!DOCTYPE HTML><html><head>
<title>Sample gallery</title>
<link rel="stylesheet" TYPE="text/css" HREF="index.css">
</head><body>
<!-- BeginTitle -->
<span class="gallerytitle">{gallery_title}</span>
<!-- EndTitle -->
{''.join(cells)}
</body></html>
""".encode("utf-8")
        pages[f"{self.BASE}/index.html"] = (200, html)
        pages[f"{self.BASE}/Gallery.arl"] = (200, b"arl")
        return pages

    def given_windows1255_standard_arles_site(
        self, *, item_id: str = "img_101"
    ) -> Dict[str, Tuple[int, bytes]]:
        return {
            f"{self.BASE}/index.html": (
                200,
                self.windows1255_standard_index_html(item_id=item_id),
            ),
            f"{self.BASE}/imagepages/{item_id}.html": (
                200,
                self.windows1255_image_page_html(item_id=item_id),
            ),
            f"{self.BASE}/hrimages/{item_id}hr.jpg": (200, self.TINY_JPEG),
            f"{self.BASE}/Gallery.arl": (404, b""),
        }

    def given_standard_arles_site_with_missing_image_page(
        self,
        *,
        ok_id: str = "img_201",
        missing_id: str = "img_299",
    ) -> Dict[str, Tuple[int, bytes]]:
        index = f"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html><head>
  <link rel="stylesheet" TYPE="text/css" HREF="index.css">
</head><body>
  <!-- BeginTitle -->
  <span class="gallerytitle">Sample Missing Page Album</span>
  <!-- EndTitle -->
  <a href="imagepages/{ok_id}.html"><img src="thumbnails/TN_{ok_id}.JPG"></a>
  <a href="imagepages/{missing_id}.html"><img src="thumbnails/TN_{missing_id}.JPG"></a>
</body></html>
""".encode("ascii")
        page_ok = f"""<html><body>
<div class="imagetitle">{ok_id}</div>
<img src="../hrimages/{ok_id}hr.jpg">
</body></html>
""".encode("ascii")
        return {
            f"{self.BASE}/index.html": (200, index),
            f"{self.BASE}/imagepages/{ok_id}.html": (200, page_ok),
            f"{self.BASE}/imagepages/{missing_id}.html": (404, b"missing"),
            f"{self.BASE}/hrimages/{ok_id}hr.jpg": (200, self.TINY_JPEG),
            f"{self.BASE}/Gallery.arl": (404, b""),
        }

    # --- HTML builders ---

    def single_image_viewer_index_html(
        self, *, item_id: str, caption: str
    ) -> str:
        """Index that is itself the Arles image viewer (not a thumbnail grid)."""
        return f"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
<title>{item_id}.jpg</title>
<link rel="stylesheet" TYPE="text/css" HREF="image.css" />
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<script language="JavaScript" type="text/javascript"><!--
// Copyright 2001-2003 Digital Dutch (www.digitaldutch.com)
//--></script>
</head>
<body>
<a href="http://photos.example/" target="_top">
<img src="./icons/home.gif" border="0" alt="Home" /></a>
<a href="index.html">
<img src="./images/{item_id}.jpg" alt="{item_id}.jpg"
 title="{item_id}.jpg" width="800" height="600" border="0" /></a>
<div class="imagetitle">{caption}</div>
</body>
</html>
"""

    def windows1255_standard_index_html(self, *, item_id: str) -> bytes:
        head = (
            b'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">\n'
            b"<html><head>\n"
            b'  <link rel="stylesheet" TYPE="text/css" HREF="index.css">\n'
            b"</head><body>\n"
            b"  <!-- BeginTitle -->\n"
            b'  <span class="gallerytitle">'
        )
        tail = (
            b"</span>\n"
            b"  <!-- EndTitle -->\n"
            + (
                f'  <a href="imagepages/{item_id}.html">'
                f'<img src="thumbnails/TN_{item_id}.JPG"></a>\n'
                f"</body></html>\n"
            ).encode("ascii")
        )
        return head + self.HEBREW_TITLE_1255 + tail

    def windows1255_image_page_html(self, *, item_id: str) -> bytes:
        return (
            b"<html><body>\n"
            b'<div class="imagetitle">'
            + self.HEBREW_TITLE_1255
            + b"</div>\n"
            + f'<img src="../hrimages/{item_id}hr.jpg">\n</body></html>\n'.encode(
                "ascii"
            )
        )

    # --- success assertions (red until product supports these shapes) ---

    def assert_folder_parse_succeeds_with_items(
        self,
        root: Path,
        *,
        item_ids: Tuple[str, ...],
        title: str | None = None,
    ) -> AlbumPreview:
        preview = self.parse(root)
        assert [item.id for item in preview.items] == list(item_ids)
        if title is not None:
            assert preview.title == title
        return preview

    def assert_scrape_and_parse_succeeds_with_items(
        self,
        pages: Dict[str, Tuple[int, bytes]],
        *,
        item_ids: Tuple[str, ...],
        title: str | None = None,
    ) -> AlbumPreview:
        result = self.scrape(f"{self.BASE}/index.html", pages)
        assert (result.album_root / "hrimages").is_dir()
        return self.assert_folder_parse_succeeds_with_items(
            result.album_root,
            item_ids=item_ids,
            title=title,
        )

    def assert_scrape_skips_missing_image_page_and_keeps_ok_items(
        self,
        pages: Dict[str, Tuple[int, bytes]],
        *,
        ok_ids: Tuple[str, ...],
        missing_id: str,
    ) -> AlbumPreview:
        preview = self.assert_scrape_and_parse_succeeds_with_items(
            pages,
            item_ids=ok_ids,
        )
        assert missing_id not in {item.id for item in preview.items}
        return preview

    def assert_scrape_rejects_as_not_arles(
        self, pages: Dict[str, Tuple[int, bytes]]
    ) -> None:
        """Intentional reject for non-photo stubs (desired end state)."""
        from src.export.scrape.scraper import NotArlesGalleryError

        with pytest.raises(NotArlesGalleryError):
            self.scrape(f"{self.BASE}/index.html", pages)

    def assert_detect_unknown_with_no_items(self, html: bytes) -> None:
        from src.export.scrape.detect import ArlesPageKind

        info = detect_arles_page(html, page_url=f"{self.BASE}/index.html")
        assert info.kind is ArlesPageKind.UNKNOWN
        assert info.items == ()
        assert info.is_arles is False


# Back-compat alias while tests migrate.
AlbumCompatFailureSuite = AlbumCompatSuite

