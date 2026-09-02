"""JobStore / orchestrator / scrape-service / event-bus suites."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional
from unittest.mock import MagicMock

import pytest

from src.export.parser import AlbumExportParser
from src.export.preview import AlbumPreview
from src.jobs.events import JobEventBus
from src.jobs.orchestrator import JobOrchestrator
from src.jobs.scrape import ScrapeService
from src.jobs.store import JobStore
from src.jobs.tokens import AccessTokenVault
from src.jobs.workspace import JobWorkspace
from tests.support.builders import PreviewBuilder, PreviewItemBuilder
from tests.support.fakes.scraper import FakeAlbumScraper
from tests.support.suites.tmp import TmpPathSuite
from tests.support.waits import JobWaiter


class JobStoreSuite(TmpPathSuite):
    """JobStore helpers under ``self.tmp_path`` (not process-global)."""

    def make_store(self, tmp_path: Path | None = None) -> JobStore:
        root = tmp_path if tmp_path is not None else self.tmp_path
        self.store = JobStore.load(root)
        return self.store


class OrchestratorSuite(JobStoreSuite):
    """JobStore + event bus + waiter; call ``make_orch`` for the cap under test."""

    @pytest.fixture(autouse=True)
    def _bind_orch_waiter(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.waiter = JobWaiter(timeout=3.0)

    def make_orch(self, max_concurrent: int = 1) -> JobOrchestrator:
        self.orch = JobOrchestrator(self.store, max_concurrent=max_concurrent)
        return self.orch

    def wait_status(self, job_id: str, status: str, timeout: float = 3.0) -> None:
        self.waiter.store_status(self.store, job_id, status, timeout=timeout)

    def wait_snapshot(
        self,
        key: str,
        *,
        minimum: int = 1,
        timeout: float = 3.0,
    ) -> Any:
        return self.waiter.snapshot(self.orch, key, minimum=minimum, timeout=timeout)


class ScrapeServiceSuite(JobStoreSuite):
    """ScrapeService + FakeAlbumScraper + JobEventBus."""

    @pytest.fixture(autouse=True)
    def _bind_scrape_tmp(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.bus = JobEventBus()
        self.scraper = FakeAlbumScraper()

    def make_service(
        self,
        scraper: Any | None = None,
        *,
        events: JobEventBus | None = None,
    ) -> ScrapeService:
        fake = scraper if scraper is not None else FakeAlbumScraper()
        self.scraper = fake
        bus = events if events is not None else self.bus
        self.service = ScrapeService(
            store=self.store,
            scraper=fake,
            parser=AlbumExportParser(),
            events=bus,
            workspace=JobWorkspace,
            jobs_root=self.tmp_path,
        )
        return self.service


class EventBusSuite:
    """In-memory JobEventBus with subscribe helpers."""

    def setup_method(self) -> None:
        self.bus = JobEventBus()
        self.persisted: list = []

    def next_event(self, subscription: Any) -> Any:
        from queue import Queue

        if isinstance(subscription, Queue):
            return subscription.get_nowait()
        getter = getattr(subscription, "get_nowait", None)
        if callable(getter):
            return getter()
        getter = getattr(subscription, "get", None)
        if callable(getter):
            return getter(timeout=0)
        return next(iter(subscription))

    def queue_empty(self, subscription: Any) -> bool:
        from queue import Queue

        if isinstance(subscription, Queue):
            return subscription.empty()
        empty = getattr(subscription, "empty", None)
        if callable(empty):
            return empty()
        qsize = getattr(subscription, "qsize", None)
        if callable(qsize):
            return qsize() == 0
        return True


class TokenVaultSuite:
    """AccessTokenVault instance per test."""

    def setup_method(self) -> None:
        self.vault = AccessTokenVault()


class WorkspaceSuite(TmpPathSuite):
    """JobWorkspace materialize tests."""

    JPEG_BYTES = b"\xff\xd8\xff\xd9"
    HTML_BYTES = b"<html><body>index</body></html>"

    @pytest.fixture(autouse=True)
    def _bind_workspace(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.root = tmp_path / "job"
        self.workspace = JobWorkspace(self.root)


class MockJobServiceSuite(TmpPathSuite):
    """MagicMock store/parser/events for ingest / publish / reprocess unit tests."""

    def setup_method(self) -> None:
        self.store = MagicMock()
        self.events = MagicMock()
        self.parser = MagicMock()
        self.workspace = MagicMock()
        self.publisher = MagicMock()
        self.gp_factory = MagicMock()

    def preview(self, title: str = "Mini album") -> AlbumPreview:
        return (
            PreviewBuilder()
            .with_title(title)
            .no_journal()
            .with_items(
                PreviewItemBuilder()
                .with_caption("hello")
                .with_size(4)
                .with_last_modified(None)
                .with_taken_on(None)
                .build()
            )
            .build()
        )

    def mock_job(
        self,
        tmp_path: Path | None = None,
        preview: AlbumPreview | None = None,
        *,
        job_id: str = "job-1",
        status: str = "pending",
        job_type: str = "preview",
        product_url: Optional[str] = None,
    ) -> MagicMock:
        root = tmp_path if tmp_path is not None else self.tmp_path
        job = MagicMock()
        job.id = job_id
        job.root = root / "jobs" / job_id
        job.status = status if preview is None else (
            status if status != "pending" else "done"
        )
        job.type = job_type
        job.preview = preview
        job.error = None
        job.product_url = product_url
        job.source_job_id = None
        return job

    def wire_ensure_local_root(self, job: MagicMock) -> None:
        self.store.ensure_local_root.return_value = job.root

    def emit_stages(self) -> List[str]:
        return [call.args[1] for call in self.events.emit.call_args_list]

    def files(self) -> list:
        return [
            ("index.html", b"<html></html>", None),
            ("hrimages/a.jpg", b"jpeg", 1343901600.0),
        ]
