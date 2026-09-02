"""Base suites for shared use cases. Not collected (no Test prefix)."""
from __future__ import annotations

from tests.support.suites.api import ApiClientSuite, ScrapeFakeSuite
from tests.support.suites.export import (
    AlbumCompatFailureSuite,
    AlbumCompatSuite,
    ArlesHttpScrapeSuite,
    DetectSuite,
    EtaSuite,
    OAuthSecretsSuite,
    ParserSuite,
    PreviewEditorSuite,
    ProgressSuite,
    PublisherSuite,
    TimestampSuite,
    VideoPreviewSuite,
)
from tests.support.suites.jobs import (
    EventBusSuite,
    JobStoreSuite,
    MockJobServiceSuite,
    OrchestratorSuite,
    ScrapeServiceSuite,
    TokenVaultSuite,
    WorkspaceSuite,
)
from tests.support.suites.persistence import ArtifactStoreSuite, StateStoreSuite
from tests.support.suites.tmp import TmpPathSuite

__all__ = [
    "AlbumCompatFailureSuite",
    "AlbumCompatSuite",
    "ApiClientSuite",
    "ArlesHttpScrapeSuite",
    "ArtifactStoreSuite",
    "DetectSuite",
    "EtaSuite",
    "EventBusSuite",
    "JobStoreSuite",
    "MockJobServiceSuite",
    "OAuthSecretsSuite",
    "OrchestratorSuite",
    "ParserSuite",
    "PreviewEditorSuite",
    "ProgressSuite",
    "PublisherSuite",
    "ScrapeFakeSuite",
    "ScrapeServiceSuite",
    "StateStoreSuite",
    "TimestampSuite",
    "TmpPathSuite",
    "TokenVaultSuite",
    "VideoPreviewSuite",
    "WorkspaceSuite",
]
