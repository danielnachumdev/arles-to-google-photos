"""Test doubles: scrapers, HTTP clients, sinks, publishers, GCS."""
from __future__ import annotations

from tests.support.fakes.gcs import FakeBlob, FakeBucket, FakeGcsClient
from tests.support.fakes.http import FakeClock, FakeHttpClient
from tests.support.fakes.publisher import fake_publisher
from tests.support.fakes.scraper import FakeAlbumScraper
from tests.support.fakes.sinks import RecordingSink

__all__ = [
    "FakeAlbumScraper",
    "FakeBlob",
    "FakeBucket",
    "FakeClock",
    "FakeGcsClient",
    "FakeHttpClient",
    "RecordingSink",
    "fake_publisher",
]
