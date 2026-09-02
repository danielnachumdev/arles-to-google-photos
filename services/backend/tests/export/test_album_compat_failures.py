"""Red-phase TDD: legacy/live album shapes that must succeed (except stubs).

Target matrix once product support lands:

| Shape                         | Folder parse     | Scrape + parse              |
|-------------------------------|------------------|-----------------------------|
| Flat ``*hr.jpg`` in root      | items present    | standard tree + items       |
| Flat ``*tn.jpg`` in root      | items present    | standard tree + items       |
| Standard Arles + Win-1255 HTML| UTF-8-safe parse | download + parse            |
| Missing live image page       | (n/a)            | skip missing, keep OK items |
| Flash / non-photo stub        | reject           | ``NotArlesGalleryError``    |
| Nested media (any folders)    | linked + resolve | direct media download       |
| Single-image viewer index     | caption + item   | content ``img`` + parse     |
"""
from __future__ import annotations

from tests.support.suites import AlbumCompatSuite


class TestFlatLegacyHrSuffixAlbum(AlbumCompatSuite):
    """Flat root preview + ``*hr.jpg`` beside ``index.html``."""

    def test_folder_parse_includes_hr_photo(self) -> None:
        album = self.given_flat_legacy_hr_suffix_album()
        self.assert_folder_parse_succeeds_with_items(
            album,
            item_ids=("img_001",),
            title=self.FLAT_HR_TITLE,
        )

    def test_scrape_materializes_parser_compatible_album(self) -> None:
        self.assert_scrape_and_parse_succeeds_with_items(
            self.given_flat_legacy_hr_suffix_site(),
            item_ids=("img_001",),
            title=self.FLAT_HR_TITLE,
        )


class TestFlatLegacyTnSuffixAlbum(AlbumCompatSuite):
    """Flat root ``name.jpg`` + ``nametn.jpg``."""

    def test_folder_parse_includes_photo(self) -> None:
        album = self.given_flat_legacy_tn_suffix_album()
        self.assert_folder_parse_succeeds_with_items(
            album,
            item_ids=("img_002",),
            title=self.FLAT_TN_TITLE,
        )

    def test_scrape_materializes_parser_compatible_album(self) -> None:
        self.assert_scrape_and_parse_succeeds_with_items(
            self.given_flat_legacy_tn_suffix_site(),
            item_ids=("img_002",),
            title=self.FLAT_TN_TITLE,
        )


class TestWindows1255StandardArlesAlbum(AlbumCompatSuite):
    """Modern Arles folders whose HTML is Windows-1255, not UTF-8."""

    def test_folder_parse_reads_hebrew_title_and_items(self) -> None:
        album = self.given_windows1255_standard_arles_album()
        self.assert_folder_parse_succeeds_with_items(
            album,
            item_ids=("img_101",),
            title=self.HEBREW_TITLE,
        )

    def test_scrape_then_parse_reads_hebrew_title_and_items(self) -> None:
        self.assert_scrape_and_parse_succeeds_with_items(
            self.given_windows1255_standard_arles_site(),
            item_ids=("img_101",),
            title=self.HEBREW_TITLE,
        )


class TestMissingRemoteImagePage(AlbumCompatSuite):
    """One listed ``imagepages/`` URL 404s; keep the rest."""

    def test_scrape_skips_missing_page_and_keeps_ok_photos(self) -> None:
        pages = self.given_standard_arles_site_with_missing_image_page()
        self.assert_scrape_skips_missing_image_page_and_keeps_ok_items(
            pages,
            ok_ids=("img_201",),
            missing_id="img_299",
        )


class TestStubFlashNonPhotoAlbum(AlbumCompatSuite):
    """Flash / non-photo stub — intentional reject."""

    def test_scrape_rejects_as_not_arles(self) -> None:
        self.assert_scrape_rejects_as_not_arles(self.given_stub_flash_site())

    def test_detect_marks_page_unknown_with_no_gallery_items(self) -> None:
        html = self.given_stub_flash_site()[f"{self.BASE}/index.html"][1]
        self.assert_detect_unknown_with_no_items(html)


class TestNestedVideoGalleryAlbum(AlbumCompatSuite):
    """Deep nested media under arbitrary folders (not only ``video/`` / ``images/``)."""

    def test_detect_finds_nested_video_items(self) -> None:
        from src.export.scrape.detect import ArlesPageKind, detect_arles_page

        pages = self.given_nested_video_gallery_site()
        html = pages[f"{self.BASE}/index.html"][1]
        info = detect_arles_page(
            html, page_url=f"{self.BASE}/index.html", has_gallery_arl=True
        )
        assert info.kind is ArlesPageKind.LEAF
        assert [item.item_id for item in info.items] == list(self.NESTED_VIDEO_IDS)
        assert "direct_media_grid" in info.fingerprints

    def test_scrape_prefers_full_size_sibling_and_parses(self) -> None:
        pages = self.given_nested_video_gallery_site()
        result = self.scrape(f"{self.BASE}/index.html", pages)
        hr = sorted((result.album_root / "hrimages").iterdir())
        assert len(hr) == 3
        assert all(path.read_bytes().startswith(b"wmv-full-") for path in hr)
        preview = self.assert_folder_parse_succeeds_with_items(
            result.album_root,
            item_ids=self.NESTED_VIDEO_IDS,
            title=self.NESTED_VIDEO_TITLE,
        )
        assert all(item.kind == "video" for item in preview.items)


class TestSingleImageViewerAlbum(AlbumCompatSuite):
    """Arles image viewer used as the album index (no thumbnail grid)."""

    def test_detect_finds_content_image_and_caption_title(self) -> None:
        from src.export.scrape.detect import ArlesPageKind, detect_arles_page

        pages = self.given_single_image_viewer_site()
        html = pages[f"{self.BASE}/index.html"][1]
        info = detect_arles_page(
            html,
            page_url=f"{self.BASE}/index.html",
            has_gallery_arl=True,
        )
        assert info.is_arles is True
        assert info.kind is ArlesPageKind.LEAF
        assert [item.item_id for item in info.items] == [self.VIEWER_ITEM_ID]
        assert info.items[0].image_page_href == f"images/{self.VIEWER_ITEM_ID}.jpg"
        assert info.gallery_title == self.VIEWER_CAPTION
        assert "image_css" in info.fingerprints
        assert "imagetitle" in info.fingerprints
        assert "direct_media_grid" in info.fingerprints

    def test_folder_parse_reads_caption_without_loose_fallback(self) -> None:
        album = self.given_single_image_viewer_album()
        preview = self.assert_folder_parse_succeeds_with_items(
            album,
            item_ids=(self.VIEWER_ITEM_ID,),
            title=self.VIEWER_CAPTION,
        )
        assert preview.structure_fallback is False
        assert preview.items[0].caption == self.VIEWER_CAPTION
        assert preview.items[0].relpath == f"hrimages/{self.VIEWER_ITEM_ID}hr.JPG"

    def test_scrape_then_parse_keeps_caption(self) -> None:
        preview = self.assert_scrape_and_parse_succeeds_with_items(
            self.given_single_image_viewer_site(),
            item_ids=(self.VIEWER_ITEM_ID,),
            title=self.VIEWER_CAPTION,
        )
        assert preview.structure_fallback is False
        assert preview.items[0].caption == self.VIEWER_CAPTION


class TestTrailingHrImagepagesAlbum(AlbumCompatSuite):
    """``imagepages/{id}hr.html`` must normalize to the same id as ``hrimages/{id}hr.*``."""

    def test_detect_normalizes_trailing_hr_item_id(self) -> None:
        from src.export.scrape.detect import ArlesPageKind, detect_arles_page

        pages = self.given_trailing_hr_imagepages_site()
        html = pages[f"{self.BASE}/index.html"][1]
        info = detect_arles_page(
            html,
            page_url=f"{self.BASE}/index.html",
            has_gallery_arl=True,
        )
        assert info.kind is ArlesPageKind.LEAF
        assert [item.item_id for item in info.items] == [self.HR_PAGE_ITEM_ID]
        assert info.items[0].image_page_href == (
            f"imagepages/{self.HR_PAGE_ITEM_ID}hr.html"
        )

    def test_folder_parse_matches_hrimages_without_fallback(self) -> None:
        album = self.given_trailing_hr_imagepages_album()
        preview = self.assert_folder_parse_succeeds_with_items(
            album,
            item_ids=(self.HR_PAGE_ITEM_ID,),
            title=self.HR_PAGE_TITLE,
        )
        assert preview.structure_fallback is False
        assert preview.items[0].caption == self.HR_PAGE_CAPTION
        assert preview.items[0].relpath == f"hrimages/{self.HR_PAGE_ITEM_ID}hr.JPG"

    def test_scrape_then_parse_keeps_normalized_id_and_caption(self) -> None:
        preview = self.assert_scrape_and_parse_succeeds_with_items(
            self.given_trailing_hr_imagepages_site(),
            item_ids=(self.HR_PAGE_ITEM_ID,),
            title=self.HR_PAGE_TITLE,
        )
        assert preview.structure_fallback is False
        assert preview.items[0].caption == self.HR_PAGE_CAPTION
