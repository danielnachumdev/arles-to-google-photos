"""Declarative test support: builders, fakes, strategies, and suites."""
from __future__ import annotations

from tests.support.album import AlbumTree
from tests.support.api import MigratorApi
from tests.support.builders import JobRecordBuilder, PreviewBuilder, PreviewItemBuilder
from tests.support.fakes.http import FakeClock, FakeHttpClient
from tests.support.fakes.publisher import fake_publisher
from tests.support.fakes.scraper import FakeAlbumScraper
from tests.support.fakes.sinks import RecordingSink
from tests.support.persistence import (
    JsonStateStoreBackend,
    SqlAlchemyUrlStateStoreBackend,
    SqliteStateStoreBackend,
    StateStoreBackend,
    state_store_backends,
)
from tests.support.waits import JobWaiter

__all__ = [
    "AlbumTree",
    "FakeAlbumScraper",
    "FakeClock",
    "FakeHttpClient",
    "JobRecordBuilder",
    "JobWaiter",
    "JsonStateStoreBackend",
    "MigratorApi",
    "PreviewBuilder",
    "PreviewItemBuilder",
    "RecordingSink",
    "SqlAlchemyUrlStateStoreBackend",
    "SqliteStateStoreBackend",
    "StateStoreBackend",
    "fake_publisher",
    "state_store_backends",
]
