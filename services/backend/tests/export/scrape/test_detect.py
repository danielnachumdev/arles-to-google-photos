"""TDD: Arles HTML gallery detection (leaf vs parent vs hub, fingerprints, order)."""
from __future__ import annotations

import pytest

from src.export.scrape.detect import ArlesPageKind, detect_arles_page, video_embed_urls
from tests.conftest import DAY1_REAL, FIXTURES
from tests.support.suites import DetectSuite

HUB_INDEX = (FIXTURES / "arles_hub_index.html").read_text(encoding="utf-8")
WMV_LEAF_INDEX = (FIXTURES / "arles_embed_wmv" / "index.html").read_text(encoding="utf-8")
WMV_IMAGE_PAGE = (
    FIXTURES / "arles_embed_wmv" / "imagepages" / "0512_1_06[1].html"
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

LEAF_INDEX = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>2/8/2012 - Day1</title>
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
  <!-- BeginTable -->
  <table width="100%">
    <tr bgcolor="#FFFFFF">
      <td align="center"><a href="imagepages/20120802_01.html"><img
            src="thumbnails/TN_20120802_01.JPG" alt="20120802_01.JPG"></a></td>
      <td align="center"><a href="imagepages/20120802_02.html"><img
            src="thumbnails/TN_20120802_02.JPG" alt="20120802_02.JPG"></a></td>
    </tr>
  </table>
  <!-- EndTable -->
  <table width="100%">
    <tr>
      <td align="center"><a href="../index.html" target="_top">Home</a></td>
      <td align="center"><a href="index2.html">Next index page</a></td>
    </tr>
  </table>
  <div class="WordSection1" dir="RTL">
    <p class="MsoNormal"><b>יומן</b></p>
    <p class="MsoNormal">היום יצאנו לטיול.</p>
  </div>
</body>
</html>
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
  <!-- BeginSubCategories -->
  <table>
    <tr>
      <td><a href="Day1/index.html"><img
            src="Day1/thumbnails/TN_20120802_01.JPG" alt="Day1"></a></td>
      <td><a href="Day2/index.html"><img
            src="Day2/thumbnails/TN_20120803_01.JPG" alt="Day2"></a></td>
    </tr>
  </table>
  <!-- EndSubCategories -->
  <a href="../index.html">Home</a>
</body>
</html>
"""

IMAGE_PAGE = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>20120802_01.JPG</title>
  <link rel="stylesheet" TYPE="text/css" HREF="image.css">
  <script language="JavaScript" type="text/javascript"><!--
// Copyright 2001-2007 Digital Dutch (www.digitaldutch.com)
//--></script>
</head>
<body>
  <div class="imagetitle">כיתוב ראשון</div>
  <a href="20120802_02.html"><img src="../images/20120802_01.JPG" alt="20120802_01.JPG"></a>
</body>
</html>
"""

RANDOM_HTML = """<!DOCTYPE html>
<html><head><title>Blog</title></head>
<body><h1>Hello</h1><p>Not a gallery.</p></body></html>
"""

YEAR_TOC_HTML = """<!DOCTYPE html>
<html><head><title>2012 albums</title></head>
<body>
  <h1>2012</h1>
  <p><a href="2012/1212_1/index.html">December trip 1</a></p>
  <p><a href="2012/1212_2/index.html">December trip 2</a></p>
</body></html>
"""




























class TestDetectArlesPage(DetectSuite):
    def test_leaf_index_is_arles_with_grid_order(self) -> None:
        info = detect_arles_page(
            LEAF_INDEX,
            page_url="http://photos.example/2012/Day1/index.html",
        )

        assert info.is_arles is True
        assert info.kind is ArlesPageKind.LEAF
        assert info.gallery_title == "2/8/2012 - Day1"
        assert [item.item_id for item in info.items] == ["20120802_01", "20120802_02"]
        assert info.items[0].thumbnail_src is not None
        assert "TN_20120802_01.JPG" in info.items[0].thumbnail_src
        assert info.journal_present is True
        assert "begin_title" in info.fingerprints
        assert "gallerytitle" in info.fingerprints
        assert "imagepages_grid" in info.fingerprints
        assert "thumbnail_tn" in info.fingerprints

    def test_leaf_index_ignores_home_and_treats_index2_as_pagination(self) -> None:
        info = detect_arles_page(
            LEAF_INDEX,
            page_url="http://photos.example/2012/Day1/index.html",
        )

        assert info.child_gallery_hrefs == ()
        assert info.paginated_index_hrefs == ("index2.html",)

    def test_index2_detects_sibling_index_html_and_index3_not_parent_home(self) -> None:
        """Arles page-2 nav links back to index.html and forward to index3.html."""
        html = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>Paged gallery 2</title>
  <link rel="stylesheet" TYPE="text/css" HREF="index.css">
</head>
<body>
  <!-- BeginTitle -->
  <span class="gallerytitle">1011_3</span>
  <!-- EndTitle -->
  <a href="imagepages/20111011_03.html"><img src="thumbnails/TN_20111011_03.JPG"></a>
  <table width="100%">
    <tr>
      <td align="center"><a href="../index.html" target="_top">Home</a></td>
      <td align="center"><a href="index.html"><img src="res/prev.gif" border="0" alt="הקודם"></a></td>
      <td align="center"><a href="index3.html"><img src="res/next.gif" border="0" alt="הבא"></a></td>
    </tr>
  </table>
</body>
</html>
"""
        info = detect_arles_page(
            html,
            page_url="https://albums.example/album/2011/1011_3/index2.html",
        )

        assert info.kind is ArlesPageKind.LEAF
        assert info.child_gallery_hrefs == ()
        assert info.paginated_index_hrefs == ("index.html", "index3.html")
        joined = " ".join(info.paginated_index_hrefs).lower()
        assert "../index.html" not in joined

    def test_pagination_href_from_hebrew_text_and_image_nav_buttons(self) -> None:
        html = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
  <title>Paged</title>
  <link rel="stylesheet" TYPE="text/css" HREF="index.css">
</head>
<body>
  <!-- BeginTitle -->
  <span class="gallerytitle">Paged</span>
  <!-- EndTitle -->
  <a href="imagepages/20111011_01.html"><img src="thumbnails/TN_20111011_01.JPG"></a>
  <a href="index2.html">הבא</a>
  <a href="index2.html"><input type="image" src="res/next.gif" alt="Next"></a>
</body>
</html>
"""
        info = detect_arles_page(
            html,
            page_url="https://albums.example/album/2011/1011_3/index.html",
        )

        assert info.paginated_index_hrefs == ("index2.html",)

    def test_parent_index_lists_child_galleries_not_photos(self) -> None:
        info = detect_arles_page(
            PARENT_INDEX,
            page_url="http://photos.example/2012/index.html",
        )

        assert info.is_arles is True
        assert info.kind is ArlesPageKind.PARENT
        assert info.gallery_title == "Trip 2012"
        assert info.items == ()
        assert info.child_gallery_hrefs == (
            "Day1/index.html",
            "Day2/index.html",
        )

    def test_parent_index_ignores_upward_home_link(self) -> None:
        info = detect_arles_page(
            PARENT_INDEX,
            page_url="http://photos.example/2012/index.html",
        )

        joined = " ".join(info.child_gallery_hrefs).lower()
        assert "../index.html" not in joined
        assert "photos.example/index.html" not in joined

    def test_hub_index_is_not_classic_arles_parent(self) -> None:
        info = detect_arles_page(
            HUB_INDEX,
            page_url="http://photos.example/2012/hub1/index.html",
        )

        assert info.kind is ArlesPageKind.HUB
        assert info.is_arles is False
        assert info.items == ()
        assert info.child_gallery_hrefs == HUB_CHILD_HREFS
        assert "mso_table" in info.fingerprints
        assert HUB_INDEX.lower().count("day1/index.html") == 2
        assert "https://example.com/" not in " ".join(info.child_gallery_hrefs)

    def test_hub_index_ignores_home_mailto_and_javascript(self) -> None:
        html = HUB_INDEX.replace(
            "</table>",
            "</table>"
            '<a href="mailto:x@example.com">mail</a>'
            '<a href="javascript:void(0)">js</a>'
            '<a href="../index.html">up</a>',
        )
        info = detect_arles_page(
            html,
            page_url="http://photos.example/2012/hub1/index.html",
        )

        assert info.kind is ArlesPageKind.HUB
        assert info.child_gallery_hrefs == HUB_CHILD_HREFS

    def test_leaf_index_is_not_classified_as_hub(self) -> None:
        info = detect_arles_page(
            LEAF_INDEX,
            page_url="http://photos.example/2012/Day1/index.html",
        )

        assert info.kind is ArlesPageKind.LEAF
        assert info.kind is not ArlesPageKind.HUB
        assert info.child_gallery_hrefs == ()

    def test_wmv_leaf_index_is_arles_and_decodes_bracket_item_id(self) -> None:
        info = detect_arles_page(
            WMV_LEAF_INDEX,
            page_url="https://albums.example/0512_1/index.html",
        )

        assert info.is_arles is True
        assert info.kind is ArlesPageKind.LEAF
        assert info.gallery_title == "May 2012 – Day 1"
        assert [item.item_id for item in info.items] == ["0512_1_05", "0512_1_06[1]"]
        assert info.items[1].image_page_href == "imagepages/0512_1_06[1].html"
        assert "gallerytitle" in info.fingerprints
        assert "imagepages_grid" in info.fingerprints
        assert "index_css" in info.fingerprints
        assert "begin_title" in info.fingerprints

    def test_image_page_detects_wmp_video_embed(self) -> None:
        page_url = "https://albums.example/0512_1/imagepages/0512_1_06[1].html"
        info = detect_arles_page(WMV_IMAGE_PAGE, page_url=page_url)

        assert info.is_arles is True
        assert "digital_dutch" in info.fingerprints
        assert "embed_video" in info.fingerprints
        assert video_embed_urls(WMV_IMAGE_PAGE, page_url=page_url) == (
            "https://albums.example/0512_1/imagepages/0512_1_06.wmv",
        )

    def test_image_page_fingerprints_digital_dutch(self) -> None:
        info = detect_arles_page(
            IMAGE_PAGE,
            page_url="http://photos.example/2012/Day1/imagepages/20120802_01.html",
        )

        assert info.is_arles is True
        assert "digital_dutch" in info.fingerprints
        assert "imagetitle" in info.fingerprints
        assert "image_css" in info.fingerprints

    def test_gallery_arl_flag_counts_as_fingerprint(self) -> None:
        info = detect_arles_page(
            "<html><body>bare</body></html>",
            page_url="http://photos.example/2012/Day1/index.html",
            has_gallery_arl=True,
        )

        assert info.is_arles is True
        assert "gallery_arl" in info.fingerprints

    def test_random_html_is_not_arles(self) -> None:
        info = detect_arles_page(RANDOM_HTML, page_url="http://example.com/post.html")

        assert info.is_arles is False
        assert info.kind is ArlesPageKind.UNKNOWN
        assert info.items == ()
        assert info.child_gallery_hrefs == ()

    def test_nested_trip_parent_lists_day_albums(self) -> None:
        """Trip folder under a year still enqueues one-segment day children."""
        info = detect_arles_page(
            PARENT_INDEX,
            page_url="https://albums.example/album/2012/0812_1/index.html",
        )

        assert info.kind is ArlesPageKind.PARENT
        assert info.child_gallery_hrefs == (
            "Day1/index.html",
            "Day2/index.html",
        )

    def test_decoy_imagepage_not_on_grid_is_excluded(self) -> None:
        html = LEAF_INDEX.replace(
            "</body>",
            '<p>See also <a href="imagepages/Text.html">Text</a></p></body>',
        )
        info = detect_arles_page(
            html,
            page_url="http://photos.example/2012/Day1/index.html",
        )

        ids = [item.item_id for item in info.items]
        assert "Text" not in ids
        assert ids == ["20120802_01", "20120802_02"]

    @pytest.mark.skipif(
        not (DAY1_REAL / "index.html").is_file(),
        reason="optional local album under data/ not present",
    )
    def test_detect_real_day1_index(self) -> None:
        html = (DAY1_REAL / "index.html").read_bytes()
        info = detect_arles_page(
            html,
            page_url="http://photos.example/Day1/index.html",
            has_gallery_arl=(DAY1_REAL / "Gallery.arl").is_file(),
        )

        assert info.is_arles is True
        assert info.kind is ArlesPageKind.LEAF
        assert info.gallery_title is not None
        assert info.gallery_title.startswith("2/8/2012")
        assert [item.item_id for item in info.items] == [
            f"20120802_{index:02d}" for index in range(1, 17)
        ]
        assert "Text" not in {item.item_id for item in info.items}
        assert info.journal_present is True
        assert "begin_title" in info.fingerprints
        assert "gallerytitle" in info.fingerprints
        assert "imagepages_grid" in info.fingerprints

    @pytest.mark.skipif(
        not (DAY1_REAL / "imagepages" / "20120802_01.html").is_file(),
        reason="optional local album under data/ not present",
    )
    def test_detect_real_day1_image_page_digital_dutch(self) -> None:
        html = (DAY1_REAL / "imagepages" / "20120802_01.html").read_bytes()
        info = detect_arles_page(
            html,
            page_url="http://photos.example/Day1/imagepages/20120802_01.html",
        )

        assert info.is_arles is True
        assert "digital_dutch" in info.fingerprints
        assert "imagetitle" in info.fingerprints

