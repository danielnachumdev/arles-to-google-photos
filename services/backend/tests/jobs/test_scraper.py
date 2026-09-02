"""Contract tests for jobs-layer AlbumScraper adapters (strategy wrap + normalize)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

import pytest

from src.jobs.scraper import (
    ScrapeResult,
    UnavailableAlbumScraper,
    files_from_album_root,
    load_default_scraper,
    normalize_scrape_result,
    should_spawn_preview_child,
    validate_scrape_url,
    wrap_scraper,
)
from tests.support.album import AlbumTree
from tests.support.suites import TmpPathSuite

class TestJobsScraperAdapter(TmpPathSuite):
    def test_validate_scrape_url_accepts_http_https(self) -> None:
        assert validate_scrape_url(" https://albums.example/day1 ") == (
            "https://albums.example/day1"
        )
        assert validate_scrape_url("http://albums.example/a").startswith("http://")
        with pytest.raises(ValueError, match="required"):
            validate_scrape_url("  ")
        with pytest.raises(ValueError, match="http"):
            validate_scrape_url("ftp://albums.example/a")
        with pytest.raises(ValueError, match="http"):
            validate_scrape_url("not-a-url")

    def test_unavailable_scraper_raises(self) -> None:
        with pytest.raises(RuntimeError, match="not available"):
            UnavailableAlbumScraper().scrape("https://albums.example/a")

    def test_wrap_none_is_unavailable(self) -> None:
        assert isinstance(wrap_scraper(None), UnavailableAlbumScraper)

    def test_wrap_requires_scrape_method(self) -> None:
        with pytest.raises(TypeError, match="scrape"):
            wrap_scraper(object())

    def test_wrap_instantiates_class_and_normalizes_list(self) -> None:
        class Dummy:
            def scrape(self, url: str, **_kwargs: Any) -> list:
                del url
                return [("index.html", b"<html></html>")]

        wrapped = wrap_scraper(Dummy)
        result = wrapped.scrape("https://albums.example/day1")
        assert isinstance(result, ScrapeResult)
        assert result.files[0][0] == "index.html"
        assert result.gallery_urls == ()

    def test_wrap_dir_adapter_for_arles_gallery_scraper(self) -> None:
        from src.export.scrape.scraper import ArlesGalleryScraper

        wrapped = wrap_scraper(ArlesGalleryScraper)
        assert type(wrapped).__name__ == "_DirScraperAdapter"

    def test_load_default_scraper_returns_callable_scrape(self) -> None:
        scraper = load_default_scraper()
        assert hasattr(scraper, "scrape")

    def test_normalize_already_scrape_result(self) -> None:
        raw = ScrapeResult(
            files=[("index.html", b"x", None)],
            gallery_urls=[" https://albums.example/b ", ""],
        )
        got = normalize_scrape_result(raw)
        assert got.files[0][1] == b"x"
        assert got.gallery_urls == (" https://albums.example/b ",)

    def test_normalize_album_root_attribute(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        (album / "index.html").write_bytes(b"<html></html>")
        (album / "hrimages").mkdir()
        (album / "hrimages" / "a.jpg").write_bytes(b"jpeg")
        (album / "job.json").write_text("{}", encoding="utf-8")

        @dataclass
        class DirResult:
            album_root: Path
            child_gallery_urls: tuple[str, ...] = ("https://albums.example/child",)

        got = normalize_scrape_result(DirResult(album_root=album))
        rels = {item[0] for item in got.files}
        assert "index.html" in rels
        assert "hrimages/a.jpg" in rels
        assert "job.json" not in rels
        assert got.gallery_urls == ("https://albums.example/child",)

    def test_normalize_dict_album_root_and_files(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        (album / "index.html").write_bytes(b"idx")
        from_root = normalize_scrape_result(
            {"album_root": album, "urls": ["https://albums.example/x"]}
        )
        assert from_root.files[0][0] == "index.html"
        assert from_root.gallery_urls == ("https://albums.example/x",)

        from_files = normalize_scrape_result(
            {
                "files": [("imagepages/a.html", b"<p/>", 1.5)],
                "gallery_urls": ["https://albums.example/y"],
            }
        )
        assert from_files.files[0] == ("imagepages/a.html", b"<p/>", 1.5)

    def test_normalize_object_files_and_path_payload(self, tmp_path: Path) -> None:
        blob = tmp_path / "pic.jpg"
        blob.write_bytes(b"JPEG")

        class FileObj:
            relpath = "hrimages/a.jpg"
            data = blob
            last_modified = 10.0

        class Result:
            files = [FileObj(), ("index.html", blob)]
            child_urls = ["https://albums.example/z"]

        got = normalize_scrape_result(Result())
        assert got.files[0][1] == b"JPEG"
        assert got.files[1][1] == b"JPEG"
        assert got.gallery_urls == ("https://albums.example/z",)

    def test_normalize_list_and_unsupported(self) -> None:
        got = normalize_scrape_result([("index.html", bytearray(b"x"))])
        assert got.files[0][1] == b"x"
        with pytest.raises(TypeError, match="unsupported scrape result"):
            normalize_scrape_result(123)
        with pytest.raises(ValueError, match="scrape file"):
            normalize_scrape_result([("only-relpath",)])
        with pytest.raises(TypeError, match="bytes"):
            normalize_scrape_result([("index.html", "not-bytes")])

    def test_normalize_object_missing_bytes(self) -> None:
        class BadFile:
            relpath = "a.jpg"
            content = "nope"

        class Result:
            files = [BadFile()]

        with pytest.raises(TypeError, match="bytes"):
            normalize_scrape_result(Result())

    def test_files_from_missing_dir(self, tmp_path: Path) -> None:
        assert files_from_album_root(tmp_path / "missing") == ()

    def test_should_spawn_preview_child_rules(self) -> None:
        assert should_spawn_preview_child([], []) is False
        assert should_spawn_preview_child([("index.html", b"x", None)], []) is True
        assert (
            should_spawn_preview_child(
                [("index.html", b"x", None)], ["https://albums.example/child"]
            )
            is False
        )
        assert (
            should_spawn_preview_child(
                [("hrimages/a.jpg", b"x", None)], ["https://albums.example/child"]
            )
            is True
        )
        mini = AlbumTree.mini_tuples()
        assert should_spawn_preview_child(mini, []) is True

    def test_adapted_scraper_legacy_signatures(self) -> None:
        class UrlOnly:
            def scrape(self, url: str) -> list:
                return [("index.html", f"<html>{url}</html>".encode("utf-8"))]

        wrapped = wrap_scraper(UrlOnly())
        result = wrapped.scrape("https://albums.example/day1", headers={"Cookie": "a"})
        assert b"albums.example" in result.files[0][1]

    def test_dir_adapter_ops_sink_and_typeerror_fallback(self, tmp_path: Path) -> None:
        from tests.support.fakes.sinks import RecordingSink

        class RequestScraper:
            def scrape(self, request: Any, dest: Path, sink: Any = None) -> dict:
                del sink
                (dest / "index.html").write_bytes(b"<html></html>")
                return {"album_root": dest, "gallery_urls": ()}

        wrapped = wrap_scraper(RequestScraper())
        sink = RecordingSink()
        result = wrapped.scrape(
            "https://albums.example/day1",
            headers={"Cookie": "a=1"},
            sink=sink,
            output_dir=tmp_path / "out",
        )
        assert result.files
        assert sink.ops_events

        class RequestNoSink:
            def scrape(self, request: Any, dest: Path) -> dict:
                (dest / "index.html").write_bytes(b"<html>nosink</html>")
                return {"album_root": dest}

        wrapped2 = wrap_scraper(RequestNoSink())
        result2 = wrapped2.scrape(
            "https://albums.example/day2",
            sink=RecordingSink(),
            output_dir=tmp_path / "out2",
        )
        assert result2.files[0][1] == b"<html>nosink</html>"

