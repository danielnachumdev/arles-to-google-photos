"""TDD: AlbumExportParser turns an HTML export tree into AlbumPreview."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import List, Tuple

import pytest

from src.export.parser import AlbumExportParser
from src.export.preview import AlbumPreview, PreviewItem
from tests.conftest import DAY1_REAL
from tests.support.fakes.sinks import RecordingSink
from tests.support.suites import ParserSuite

DAY1_CAPTION = "כיתוב ראשון"
DAY1_TITLE = "2/8/2012 - mini fixture"
DAY1_DESCRIPTION = "A tiny album used in unit tests"
DAY1_RELPATH = "hrimages/20120802_01hr.JPG"
DAY1_ID = "20120802_01"
ARLES_TITLE = "2/8/2012 - Day 1 – Delphi"
ARLES_HEADING = "יומן"
ARLES_CAPTION_01 = "כיתוב ראשון"
ARLES_CAPTION_02 = "כיתוב שני"

INDEX_HTML = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>{title}</title>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
</head>
<body>
  <table width="100%">
    <tr>
      <td align="center"><span class="gallerytitle">{title}</span></td>
    </tr>
    <tr>
      <td align="center"><span class="gallerydesc">{description}</span></td>
    </tr>
  </table>
  <p><a href="imagepages/{item_id}.html"><img src="thumbnails/{item_id}.jpg" alt="{item_id}"></a></p>
  {journal_html}
</body>
</html>
"""

IMAGE_PAGE_HTML = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>{title}</title>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
</head>
<body>
  {body}
</body>
</html>
"""


def _page_id_from_hr_name(image_name: str) -> str:
    stem = Path(image_name).stem
    if len(stem) > 2 and stem.lower().endswith("hr"):
        return stem[:-2]
    return stem


def _write_album(
    root: Path,
    *,
    title: str = "Album title",
    description: str = "Album description",
    image_name: str = "20120802_01hr.JPG",
    image_bytes: bytes = b"fake-jpeg",
    image_page_body: str = '<div class="imagetitle">a caption</div>',
    extra_index_files: Tuple[str, ...] = (),
    journal_html: str = "",
    write_index: bool = True,
    write_hrimages: bool = True,
    write_imagepages: bool = True,
    write_image_file: bool = True,
    write_image_page: bool = True,
) -> Path:
    item_id = _page_id_from_hr_name(image_name)
    if write_index:
        (root / "index.html").write_text(
            INDEX_HTML.format(
                title=title,
                description=description,
                item_id=item_id,
                journal_html=journal_html,
            ),
            encoding="utf-8",
        )
    for extra in extra_index_files:
        (root / extra).write_text("<html></html>", encoding="utf-8")

    hr_dir = root / "hrimages"
    pages_dir = root / "imagepages"
    if write_hrimages:
        hr_dir.mkdir()
        if write_image_file:
            (hr_dir / image_name).write_bytes(image_bytes)
    if write_imagepages:
        pages_dir.mkdir()
        if write_image_page:
            (pages_dir / f"{item_id}.html").write_text(
                IMAGE_PAGE_HTML.format(title=f"{item_id}.JPG", body=image_page_body),
                encoding="utf-8",
            )
    return root
































class TestAlbumExportParser(ParserSuite):
    def test_parse_day1_mini(self, day1_mini: Path) -> None:
        preview = AlbumExportParser().parse(day1_mini)

        assert isinstance(preview, AlbumPreview)
        assert preview.title == DAY1_TITLE
        assert preview.description == DAY1_DESCRIPTION
        assert preview.multi_index is False
        assert len(preview.items) == 1

        image = day1_mini / "hrimages" / "20120802_01hr.JPG"
        item = preview.items[0]
        assert isinstance(item, PreviewItem)
        assert item.id == DAY1_ID
        assert item.relpath == DAY1_RELPATH
        assert item.caption == DAY1_CAPTION
        assert item.kind == "image"
        assert item.thumb_relpath is None
        assert item.play_relpath is None
        assert item.size_bytes == image.stat().st_size
        assert item.taken_on == date(2012, 8, 2)
        assert item.last_modified is not None
        assert abs(
            (item.last_modified - datetime.fromtimestamp(image.stat().st_mtime)).total_seconds()
        ) < 2
        assert preview.journal is None

    def test_parse_accepts_optional_sink(self, day1_mini: Path) -> None:
        sink = RecordingSink()
        preview = AlbumExportParser().parse(day1_mini, sink=sink)

        assert preview.title == DAY1_TITLE
        assert sink.events
        assert all(stage == "parse" for stage, _message, _current, _total in sink.events)
        assert any(total == 1 for _stage, _message, _current, total in sink.events)

    def test_parse_without_sink(self, day1_mini: Path) -> None:
        preview = AlbumExportParser().parse(day1_mini, sink=None)
        assert preview.items[0].id == DAY1_ID

    def test_relpath_uses_forward_slashes(self, day1_mini: Path) -> None:
        item = AlbumExportParser().parse(day1_mini).items[0]
        assert "\\" not in item.relpath
        assert item.relpath == DAY1_RELPATH

    @pytest.mark.parametrize(
        ("missing", "match"),
        [
            ("index.html", r"missing index\.html"),
            ("hrimages", r"no photo/video files|hrimages"),
        ],
    )
    def test_missing_required_layout_raises(self, tmp_path: Path, missing: str, match: str) -> None:
        _write_album(
            tmp_path,
            write_index=missing != "index.html",
            write_hrimages=missing != "hrimages",
            write_imagepages=True,
        )
        with pytest.raises((ValueError, FileNotFoundError, OSError), match=match):
            AlbumExportParser().parse(tmp_path)

    def test_hub_like_folder_explains_parent_structure(self, tmp_path: Path) -> None:
        root = tmp_path / "Trip"
        root.mkdir()
        (root / "index.html").write_text(
            "<html><head><title>Trip</title></head><body></body></html>",
            encoding="utf-8",
        )
        for day in ("Day1", "Day2"):
            child = root / day
            child.mkdir()
            (child / "index.html").write_text("<html></html>", encoding="utf-8")
        with pytest.raises(ValueError, match=r"parent/hub folder|child albums"):
            AlbumExportParser().parse(root)

    def test_missing_imagepages_still_parses_when_hrimages_present(
        self, tmp_path: Path
    ) -> None:
        """Captions are optional; ``imagepages/`` is not required for membership."""
        _write_album(tmp_path, write_imagepages=False)
        preview = AlbumExportParser().parse(tmp_path)
        assert [item.id for item in preview.items] == ["20120802_01"]
        assert preview.items[0].caption == ""

    def test_multi_index_skips_description(self, tmp_path: Path) -> None:
        _write_album(tmp_path, extra_index_files=("index1.html",))
        preview = AlbumExportParser().parse(tmp_path)

        assert preview.multi_index is True
        assert preview.description is None
        assert preview.title == "Album title"
        assert len(preview.items) == 1

    def test_multi_index_merges_gallery_ids_from_sibling_indexes(
        self, tmp_path: Path
    ) -> None:
        """Folder exports keep index2.html; membership must include page-2 grid."""
        root = tmp_path
        (root / "hrimages").mkdir()
        (root / "imagepages").mkdir()
        for stem in ("pic01", "pic02", "pic03"):
            (root / "hrimages" / f"{stem}hr.JPG").write_bytes(b"jpeg")
            (root / "imagepages" / f"{stem}.html").write_text(
                f'<html><body><div class="imagetitle">{stem}</div></body></html>',
                encoding="utf-8",
            )
        (root / "index.html").write_text(
            """<!DOCTYPE html>
<html><body>
  <span class="gallerytitle">Paged album</span>
  <span class="gallerydesc">should be skipped</span>
  <a href="imagepages/pic01.html"><img src="thumbnails/pic01.jpg"></a>
  <a href="index2.html">Next</a>
</body></html>
""",
            encoding="utf-8",
        )
        (root / "index2.html").write_text(
            """<!DOCTYPE html>
<html><body>
  <span class="gallerytitle">Paged album</span>
  <a href="imagepages/pic02.html"><img src="thumbnails/pic02.jpg"></a>
  <a href="imagepages/pic03.html"><img src="thumbnails/pic03.jpg"></a>
  <a href="index.html">Prev</a>
</body></html>
""",
            encoding="utf-8",
        )

        preview = AlbumExportParser().parse(root)

        assert preview.multi_index is True
        assert preview.description is None
        assert [item.id for item in preview.items] == ["pic01", "pic02", "pic03"]

    def test_single_index_keeps_description(self, tmp_path: Path) -> None:
        _write_album(tmp_path)
        preview = AlbumExportParser().parse(tmp_path)

        assert preview.multi_index is False
        assert preview.description == "Album description"

    def test_missing_imagetitle_yields_empty_caption(self, tmp_path: Path) -> None:
        _write_album(tmp_path, image_page_body="<div>no title here</div>")
        preview = AlbumExportParser().parse(tmp_path)

        assert len(preview.items) == 1
        assert preview.items[0].id == DAY1_ID
        assert preview.items[0].caption == ""
        assert preview.items[0].relpath == DAY1_RELPATH

    def test_missing_image_page_yields_empty_caption(self, tmp_path: Path) -> None:
        _write_album(tmp_path, write_image_page=False)
        preview = AlbumExportParser().parse(tmp_path)

        assert len(preview.items) == 1
        assert preview.items[0].caption == ""

    def test_parse_percent_encoded_bracket_id_matches_wmv_hr_file(self, tmp_path: Path) -> None:
        root = tmp_path
        video = b"WMV" + b"V" * 1_024
        poster = b"\xff\xd8" + b"P" * 64 + b"\xff\xd9"
        play = b"ftypmp4"
        (root / "hrimages").mkdir()
        (root / "imagepages").mkdir()
        (root / "thumbnails").mkdir()
        (root / "preview").mkdir()
        (root / "hrimages" / "0512_1_06[1]hr.wmv").write_bytes(video)
        (root / "hrimages" / "0512_1_06[1]hr.jpg").write_bytes(poster)
        (root / "thumbnails" / "TN_0512_1_06[1].jpg").write_bytes(poster)
        (root / "preview" / "0512_1_06[1].mp4").write_bytes(play)
        (root / "imagepages" / "0512_1_06[1].html").write_text(
            "<html><body></body></html>",
            encoding="utf-8",
        )
        (root / "index.html").write_text(
            """<!DOCTYPE html>
    <html><body>
      <span class="gallerytitle">May 2012 – Day 1</span>
      <a href="imagepages/0512_1_06%5B1%5D.html">
        <img src="thumbnails/TN_0512_1_06%5B1%5D.jpg">
      </a>
    </body></html>
    """,
            encoding="utf-8",
        )

        preview = AlbumExportParser().parse(root)

        assert [item.id for item in preview.items] == ["0512_1_06[1]"]
        item = preview.items[0]
        assert item.relpath == "hrimages/0512_1_06[1]hr.wmv"
        assert item.size_bytes == len(video)
        assert item.caption == ""
        assert item.kind == "video"
        assert item.thumb_relpath == "thumbnails/TN_0512_1_06[1].jpg"
        assert item.play_relpath == "preview/0512_1_06[1].mp4"

    def test_parse_video_prefers_wmv_over_companion_jpeg_in_hrimages(self, tmp_path: Path) -> None:
        root = tmp_path
        video = b"WMV" + b"V" * 256
        poster = b"\xff\xd8" + b"J" * 32 + b"\xff\xd9"
        (root / "hrimages").mkdir()
        (root / "imagepages").mkdir()
        (root / "hrimages" / "clip01hr.jpg").write_bytes(poster)
        (root / "hrimages" / "clip01hr.wmv").write_bytes(video)
        (root / "imagepages" / "clip01.html").write_text(
            "<html><body><div class=\"imagetitle\">clip</div></body></html>",
            encoding="utf-8",
        )
        (root / "index.html").write_text(
            """<!DOCTYPE html>
    <html><body>
      <span class="gallerytitle">Clips</span>
      <a href="imagepages/clip01.html"><img src="thumbnails/TN_clip01.jpg"></a>
    </body></html>
    """,
            encoding="utf-8",
        )

        preview = AlbumExportParser().parse(root)

        assert len(preview.items) == 1
        item = preview.items[0]
        assert item.relpath == "hrimages/clip01hr.wmv"
        assert item.kind == "video"
        assert item.thumb_relpath == "hrimages/clip01hr.jpg"
        assert item.play_relpath is None

    def test_item_id_strips_trailing_hr_only(self, tmp_path: Path) -> None:
        _write_album(
            tmp_path,
            image_name="pic01hr.jpg",
            image_page_body='<div class="imagetitle">hello</div>',
        )
        preview = AlbumExportParser().parse(tmp_path)

        assert preview.items[0].id == "pic01"
        assert preview.items[0].relpath == "hrimages/pic01hr.jpg"
        assert preview.items[0].caption == "hello"

    def test_hr_in_middle_of_filename_is_kept(self, tmp_path: Path) -> None:
        _write_album(
            tmp_path,
            image_name="chrome.jpg",
            image_page_body='<div class="imagetitle">kept</div>',
        )
        preview = AlbumExportParser().parse(tmp_path)

        assert preview.items[0].id == "chrome"
        assert preview.items[0].relpath == "hrimages/chrome.jpg"
        assert preview.items[0].caption == "kept"

    def test_parse_day1_arles_journal_order_and_dates(self, day1_arles: Path) -> None:
        preview = AlbumExportParser().parse(day1_arles)

        assert preview.title == ARLES_TITLE
        assert preview.description is None
        assert preview.multi_index is False
        assert preview.journal is not None
        assert preview.journal.heading == ARLES_HEADING
        assert preview.journal.paragraphs == (
            "היום יצאנו לטיול.",
            "היה יום ארוך אבל נעים.",
        )
        assert "mso" not in " ".join(preview.journal.paragraphs).lower()
        assert [item.id for item in preview.items] == ["20120802_02", "20120802_01"]
        assert preview.items[0].caption == ARLES_CAPTION_02
        assert preview.items[1].caption == ARLES_CAPTION_01
        assert preview.items[0].relpath == "hrimages/20120802_02hr.JPG"
        assert preview.items[1].relpath == "hrimages/20120802_01hr.JPG"
        assert all(item.taken_on == date(2012, 8, 2) for item in preview.items)
        ids = {item.id for item in preview.items}
        assert "Text" not in ids
        assert "aaa" not in ids

    def test_multi_index_keeps_journal_from_index_html(self, tmp_path: Path) -> None:
        journal = """
        <div class="WordSection1">
          <p class="MsoNormal">יומן</p>
          <p class="MsoNormal">פסקה אחת</p>
        </div>
        """
        _write_album(tmp_path, extra_index_files=("index1.html",), journal_html=journal)
        preview = AlbumExportParser().parse(tmp_path)

        assert preview.multi_index is True
        assert preview.description is None
        assert preview.journal is not None
        assert preview.journal.heading == "יומן"
        assert preview.journal.paragraphs == ("פסקה אחת",)

    @pytest.mark.skipif(
        not (DAY1_REAL / "index.html").is_file() or not (DAY1_REAL / "hrimages").is_dir(),
        reason="optional local album under data/ not present",
    )
    def test_title_falls_back_to_first_span_when_gallerytitle_missing(self, tmp_path: Path) -> None:
        root = tmp_path
        (root / "hrimages").mkdir()
        (root / "imagepages").mkdir()
        (root / "hrimages" / "20120802_01hr.JPG").write_bytes(b"jpeg")
        (root / "imagepages" / "20120802_01.html").write_text(
            '<html><body><div class="imagetitle">c</div></body></html>',
            encoding="utf-8",
        )
        (root / "index.html").write_text(
            """<!DOCTYPE html><html><body>
            <span>Fallback title</span>
            <span>Fallback desc</span>
            <a href="imagepages/20120802_01.html"><img src="t.jpg"></a>
            </body></html>""",
            encoding="utf-8",
        )
        preview = AlbumExportParser().parse(root)
        assert preview.title == "Fallback title"
        assert preview.description == "Fallback desc"

    def test_missing_title_raises(self, tmp_path: Path) -> None:
        root = tmp_path
        (root / "hrimages").mkdir()
        (root / "imagepages").mkdir()
        (root / "hrimages" / "20120802_01hr.JPG").write_bytes(b"jpeg")
        (root / "index.html").write_text("<html><body></body></html>", encoding="utf-8")
        with pytest.raises(ValueError, match=r"no gallery title|gallerytitle"):
            AlbumExportParser().parse(root)

    def test_flash_stub_not_imported_even_with_loose_media(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "stub_flash"
        root.mkdir()
        (root / "index.html").write_text(
            "<html><head><title>Sample Flash Stub</title></head>"
            "<body><object data='gallery.swf'></object>"
            "<img src='home.gif'></body></html>",
            encoding="utf-8",
        )
        (root / "gallery.swf").write_bytes(b"FWS")
        (root / "home.gif").write_bytes(b"GIF89a" + b"\0" * 20)
        with pytest.raises(ValueError, match=r"Flash/non-photo|no photo/video"):
            AlbumExportParser().parse(root, allow_loose_media=True)
        with pytest.raises(ValueError, match=r"Flash/non-photo|no photo/video"):
            AlbumExportParser().parse(root)

    def test_google_photos_redirect_raises_before_loose_fallback(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "20210327"
        root.mkdir()
        (root / "index.html").write_text(
            """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN">
<html><head>
<meta http-equiv="REFRESH" content="0;url=https://photos.app.goo.gl/EXAMPLEONLY" />
</head><body></body></html>
""",
            encoding="utf-8",
        )
        (root / "decoy.jpg").write_bytes(b"jpeg-decoy")
        with pytest.raises(
            ValueError,
            match=r"redirects to Google Photos|photos\.app\.goo\.gl",
        ):
            AlbumExportParser().parse(root, allow_loose_media=True)
        with pytest.raises(
            ValueError,
            match=r"redirects to Google Photos|photos\.app\.goo\.gl",
        ):
            AlbumExportParser().parse(root)

    def test_generic_meta_refresh_raises_before_loose_fallback(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "moved_album"
        root.mkdir()
        (root / "index.html").write_text(
            """<!DOCTYPE HTML><html><head>
<meta http-equiv="refresh" content="0;url=https://example.com/elsewhere/" />
</head><body></body></html>
""",
            encoding="utf-8",
        )
        with pytest.raises(
            ValueError,
            match=r"redirects to another page|example\.com/elsewhere",
        ):
            AlbumExportParser().parse(root, allow_loose_media=True)

    def test_nested_video_gallery_resolves_full_size_media(
        self, tmp_path: Path
    ) -> None:
        """Deep nested media under arbitrary folders; prefer non-small videos."""
        root = tmp_path / "nested_media_album"
        preview_dir = root / "media" / "deep" / "preview"
        stills_dir = root / "media" / "stills"
        thumbs = root / "thumbnails"
        icons = root / "icons"
        for path in (preview_dir, stills_dir, thumbs, icons):
            path.mkdir(parents=True)
        (root / "index.html").write_text(
            """<!DOCTYPE HTML><html><head><title>Sample</title></head><body>
            <span class="gallerytitle">Sample Nested Video Album</span>
            <a href="media/deep/preview/clip_a_small_320x240_371Kbps.wmv">
              <img src="thumbnails/TN_clip_a.jpg"></a>
            <a href="media/deep/preview/clip_b_small_320x240_316Kbps.wmv">
              <img src="thumbnails/TN_clip_b.jpg"></a>
            <a href="media/deep/preview/clip_c_small_320x240_342Kbps.wmv">
              <img src="thumbnails/TN_clip_c.jpg"></a>
            </body></html>""",
            encoding="utf-8",
        )
        (preview_dir / "clip_a_small_320x240_371Kbps.wmv").write_bytes(b"wmv1")
        (preview_dir / "clip_b_small_320x240_316Kbps.wmv").write_bytes(b"wmv2")
        (preview_dir / "clip_c_small_320x240_342Kbps.wmv").write_bytes(b"wmv3")
        (preview_dir / "clip_a_Big.wmv").write_bytes(b"FULL-A-XXXXXXXX")
        (preview_dir / "clip_b_Big.wmv").write_bytes(b"FULL-B-XXXXXXXX")
        (preview_dir / "clip_c_Big.wmv").write_bytes(b"FULL-C-XXXXXXXX")
        (stills_dir / "clip_a.jpg").write_bytes(b"jpeg1")
        (stills_dir / "clip_b.jpg").write_bytes(b"jpeg2")
        (stills_dir / "clip_c.jpg").write_bytes(b"jpeg3")
        (thumbs / "TN_clip_a.jpg").write_bytes(b"tn1")
        (icons / "home.gif").write_bytes(b"GIF89a")

        preview = AlbumExportParser().parse(root)
        assert preview.structure_fallback is False
        assert preview.title == "Sample Nested Video Album"
        assert [item.id for item in preview.items] == [
            "clip_a",
            "clip_b",
            "clip_c",
        ]
        assert all(item.relpath.endswith("_Big.wmv") for item in preview.items)
        assert all(item.kind == "video" for item in preview.items)

    def test_loose_media_without_index_when_allowed(self, tmp_path: Path) -> None:
        root = tmp_path / "VacationPics"
        root.mkdir()
        (root / "photo_a.jpg").write_bytes(b"jpeg-a")
        (root / "clip_b.mp4").write_bytes(b"video-b")
        (root / "tn_ignore.jpg").write_bytes(b"thumb")
        preview = AlbumExportParser().parse(root, allow_loose_media=True)
        assert preview.structure_fallback is True
        assert preview.title == "VacationPics"
        assert preview.description is None
        assert preview.journal is None
        assert {item.id for item in preview.items} == {"photo_a", "clip_b"}
        assert {item.relpath for item in preview.items} == {"photo_a.jpg", "clip_b.mp4"}

    def test_loose_media_disabled_still_requires_structure(self, tmp_path: Path) -> None:
        root = tmp_path / "VacationPics"
        root.mkdir()
        (root / "photo_a.jpg").write_bytes(b"jpeg-a")
        with pytest.raises(ValueError, match=r"missing index\.html"):
            AlbumExportParser().parse(root)

    def test_missing_title_uses_folder_name_when_loose_allowed(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "DayTrip"
        root.mkdir()
        (root / "hrimages").mkdir()
        (root / "hrimages" / "20120802_01hr.JPG").write_bytes(b"jpeg")
        (root / "index.html").write_text("<html><body></body></html>", encoding="utf-8")
        preview = AlbumExportParser().parse(root, allow_loose_media=True)
        assert preview.structure_fallback is True
        assert preview.title == "DayTrip"
        assert len(preview.items) == 1
        assert preview.items[0].id == "20120802_01"

    def test_invalid_taken_on_prefix_is_none(self, tmp_path: Path) -> None:
        _write_album(tmp_path, image_name="20121399_01hr.JPG")
        preview = AlbumExportParser().parse(tmp_path)
        assert preview.items[0].id == "20121399_01"
        assert preview.items[0].taken_on is None

    def test_empty_journal_section_is_none(self, tmp_path: Path) -> None:
        journal = '<div class="WordSection1"><p class="MsoNormal">   </p></div>'
        _write_album(tmp_path, journal_html=journal)
        preview = AlbumExportParser().parse(tmp_path)
        assert preview.journal is None

    @pytest.mark.skipif(
        not (DAY1_REAL / "index.html").is_file() or not (DAY1_REAL / "hrimages").is_dir(),
        reason="optional local album under data/ not present",
    )
    def test_parse_real_day1_album(self) -> None:
        preview = AlbumExportParser().parse(DAY1_REAL)

        assert preview.title.startswith("2/8/2012")
        assert preview.description is None
        assert preview.journal is not None
        assert preview.journal.heading
        assert len(preview.journal.paragraphs) >= 2
        assert [item.id for item in preview.items] == [
            f"20120802_{index:02d}" for index in range(1, 17)
        ]
        assert preview.items[0].taken_on == date(2012, 8, 2)

