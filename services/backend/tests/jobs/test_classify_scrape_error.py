"""classify_scrape_error keeps stable codes while preserving diagnostic detail."""
from __future__ import annotations

from src.export.scrape.scraper import NotArlesGalleryError, ScrapeEmptyError, ScrapeFetchError
from src.jobs.scrape import (
    ERROR_FETCH_FAILED,
    ERROR_NOT_ARLES,
    ERROR_SCRAPE_EMPTY,
    classify_scrape_error,
)


def test_classify_fetch_keeps_original_detail() -> None:
    url = "https://albums.example/day/index.html"
    exc = ScrapeFetchError(
        f"Failed to fetch gallery index: {url} — Failed to fetch {url}: timed out",
        url=url,
        status_code=None,
    )
    code, message = classify_scrape_error(exc, url=url)
    assert code == ERROR_FETCH_FAILED
    assert "Failed to download gallery" in message
    assert url in message
    assert "timed out" in message


def test_classify_fetch_http_status_and_detail() -> None:
    url = "https://albums.example/x"
    exc = ScrapeFetchError(
        f"Failed to fetch gallery index: {url} (HTTP 503)",
        url=url,
        status_code=503,
    )
    code, message = classify_scrape_error(exc, url=url)
    assert code == ERROR_FETCH_FAILED
    assert "HTTP 503" in message
    assert "gallery index" in message or url in message


def test_classify_empty_keeps_scraper_body() -> None:
    url = "https://albums.example/empty"
    exc = ScrapeEmptyError(
        f"No album photos could be downloaded from {url} (listed 12; every HR fetch failed).",
        url=url,
    )
    code, message = classify_scrape_error(exc, url=url)
    assert code == ERROR_SCRAPE_EMPTY
    assert "No album photos found" in message
    assert "every HR fetch failed" in message


def test_classify_not_arles_keeps_detail() -> None:
    url = "https://example.com/not-arles"
    exc = NotArlesGalleryError(
        f"Not a supported Arles album: {url} (missing imagepages grid)",
        url=url,
    )
    code, message = classify_scrape_error(exc, url=url)
    assert code == ERROR_NOT_ARLES
    assert "Not a supported Arles album" in message
    assert "missing imagepages" in message
