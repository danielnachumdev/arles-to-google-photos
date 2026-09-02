"""TDD: cooperative job cancel (store, scrape, publish, ingest, HTTP)."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.export.parser import AlbumExportParser
from src.export.preview import AlbumPreview, PreviewItem
from src.jobs.cancel import CancelService
from src.jobs.events import JobEventBus
from src.jobs.ingest import IngestService
from src.jobs.orchestrator import JobOrchestrator
from src.jobs.publish import PublishService
from src.jobs.scrape import ScrapeService
from src.jobs.store import JobNotCancellableError, JobNotFoundError, JobStore
from src.jobs.workspace import JobWorkspace
from src.progress import JobCancelled, raise_if_cancelled
from tests.support.album import AlbumTree
from tests.support.api import MigratorApi
from tests.support.builders import PreviewBuilder, PreviewItemBuilder
from tests.support.fakes.scraper import FakeAlbumScraper, mini_album_files
from tests.support.suites import JobStoreSuite


def _preview(*items: PreviewItem, title: str = "Mini") -> AlbumPreview:
    if not items:
        items = (
            PreviewItemBuilder().with_id("20120802_01").with_caption("hello").with_size(4).with_last_modified(None).with_taken_on(None).build(),
            PreviewItemBuilder().with_id("20120802_02").with_caption("two").with_size(4).with_last_modified(None).with_taken_on(None).build(),
        )
    return (
        PreviewBuilder()
        .with_title(title)
        .no_journal()
        .with_items(*items)
        .build()
    )


def _scrape_service(
    tmp_path: Path,
    *,
    scraper: FakeAlbumScraper | None = None,
) -> tuple[ScrapeService, JobStore, JobEventBus]:
    store = JobStore.load(tmp_path)
    bus = JobEventBus(persist=store.append_event)
    service = ScrapeService(
        store=store,
        scraper=scraper or FakeAlbumScraper(),
        parser=AlbumExportParser(),
        events=bus,
        workspace=JobWorkspace,
        jobs_root=tmp_path,
    )
    return service, store, bus


def _mini_files() -> list[tuple[str, bytes, Optional[float]]]:
    return AlbumTree.mini_tuples()






























def _api_client(
    tmp_path: Path,
    *,
    scraper: FakeAlbumScraper | None = None,
    publisher: Any = None,
) -> TestClient:
    return MigratorApi(
        tmp_path,
        scraper=scraper or FakeAlbumScraper(),
        publisher=publisher,
        with_scraper=True,
    ).client

class TestCancel(JobStoreSuite):
    def test_request_cancel_waiting_job_marks_cancelled(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path, job_type="scrape")
        store.set_status(job.id, "waiting", job_type="scrape")
        ids = store.request_cancel(job.id)
        assert ids == [job.id]
        assert store.get(job.id).status == "cancelled"
        assert store.is_cancelled(job.id) is True

    def test_request_cancel_pending_job_marks_cancelled(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        ids = store.request_cancel(job.id)
        assert ids == [job.id]
        assert store.get(job.id).status == "cancelled"
        assert store.is_cancelled(job.id) is True

    def test_request_cancel_missing_raises(self) -> None:
        store = JobStore()
        with pytest.raises(JobNotFoundError):
            store.request_cancel("missing")

    def test_request_cancel_done_raises_not_cancellable(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        store.set_preview(job.id, _preview())
        with pytest.raises(JobNotCancellableError):
            store.request_cancel(job.id)
        assert store.get(job.id).status == "done"

    def test_request_cancel_cascades_to_running_children(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        parent = store.create(tmp_path, job_type="scrape")
        store.set_status(parent.id, "running", job_type="scrape")
        child = store.create(tmp_path, job_type="preview", parent_job_id=parent.id)
        store.set_status(child.id, "running", job_type="preview")
        done_child = store.create(tmp_path, job_type="preview", parent_job_id=parent.id)
        store.set_preview(done_child.id, _preview(title="Done child"))

        ids = store.request_cancel(parent.id)
        assert parent.id in ids
        assert child.id in ids
        assert done_child.id not in ids
        assert store.get(parent.id).status == "cancelled"
        assert store.get(child.id).status == "cancelled"
        assert store.get(done_child.id).status == "done"

    def test_request_cancel_cascades_to_pending_children_and_grandchildren(
        self,
        tmp_path: Path,
    ) -> None:
        store = JobStore.load(tmp_path)
        parent = store.create(tmp_path, job_type="scrape")
        store.set_status(parent.id, "running", job_type="scrape")
        pending_child = store.create(
            tmp_path, job_type="preview", parent_job_id=parent.id
        )
        child_scrape = store.create(
            tmp_path, job_type="scrape", parent_job_id=parent.id
        )
        store.set_status(child_scrape.id, "running", job_type="scrape")
        pending_grandchild = store.create(
            tmp_path, job_type="preview", parent_job_id=child_scrape.id
        )
        running_grandchild = store.create(
            tmp_path, job_type="upload", parent_job_id=child_scrape.id
        )
        store.set_status(running_grandchild.id, "running", job_type="upload")
        done_grandchild = store.create(
            tmp_path, job_type="upload", parent_job_id=child_scrape.id
        )
        store.mark_done(done_grandchild.id, "https://photos.example/kept")

        ids = store.request_cancel(parent.id)
        assert pending_child.id in ids
        assert child_scrape.id in ids
        assert pending_grandchild.id in ids
        assert running_grandchild.id in ids
        assert done_grandchild.id not in ids
        assert store.get(pending_child.id).status == "cancelled"
        assert store.get(child_scrape.id).status == "cancelled"
        assert store.get(pending_grandchild.id).status == "cancelled"
        assert store.get(running_grandchild.id).status == "cancelled"
        assert store.get(done_grandchild.id).status == "done"
        assert store.get(done_grandchild.id).product_url == "https://photos.example/kept"

    def test_request_cancel_hub_cancels_eight_child_scrapes_and_previews(
        self,
        tmp_path: Path,
    ) -> None:
        store = JobStore.load(tmp_path)
        hub = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/hub/index.html",
        )
        store.set_status(hub.id, "running", job_type="scrape")
        child_ids: list[str] = []
        preview_ids: list[str] = []
        for index in range(8):
            child = store.create(
                tmp_path,
                job_type="scrape",
                parent_job_id=hub.id,
                scrape_url=f"https://albums.example/hub/Day{index + 1}/index.html",
            )
            store.set_status(
                child.id,
                "pending" if index % 2 == 0 else "running",
                job_type="scrape",
            )
            preview = store.create(
                tmp_path, job_type="preview", parent_job_id=child.id
            )
            store.set_status(
                preview.id,
                "pending" if index < 7 else "running",
                job_type="preview",
            )
            child_ids.append(child.id)
            preview_ids.append(preview.id)
        store.set_preview(preview_ids[-1], _preview(title="Done day 8"))

        ids = store.request_cancel(hub.id)
        assert hub.id in ids
        for child_id in child_ids:
            assert child_id in ids
            assert store.get(child_id).status == "cancelled"
        for preview_id in preview_ids[:-1]:
            assert preview_id in ids
            assert store.get(preview_id).status == "cancelled"
        assert preview_ids[-1] not in ids
        assert store.get(preview_ids[-1]).status == "done"

    def test_cancel_service_drops_pending_orchestrator_descendants(
        self,
        tmp_path: Path,
    ) -> None:
        store = JobStore.load(tmp_path)
        orch = JobOrchestrator(store, max_concurrent=1)
        bus = JobEventBus(persist=store.append_event)
        cancel = CancelService(store=store, events=bus, drop_pending=orch.drop)

        blocker = threading.Event()
        started = threading.Event()
        occupant = store.create(tmp_path, job_type="preview")

        def occupy() -> None:
            started.set()
            blocker.wait(timeout=5)

        orch.submit(occupant.id, occupy)
        assert started.wait(timeout=2)

        parent = store.create(tmp_path, job_type="scrape")
        store.set_status(parent.id, "running", job_type="scrape")
        child = store.create(tmp_path, job_type="scrape", parent_job_id=parent.id)
        grandchild = store.create(
            tmp_path, job_type="preview", parent_job_id=child.id
        )
        child_ran = threading.Event()
        grandchild_ran = threading.Event()
        orch.submit(child.id, child_ran.set)
        orch.submit(grandchild.id, grandchild_ran.set)
        snap = orch.snapshot()
        assert child.id in snap["pending_ids"]
        assert grandchild.id in snap["pending_ids"]

        cancel.cancel(parent.id)
        assert store.get(parent.id).status == "cancelled"
        assert store.get(child.id).status == "cancelled"
        assert store.get(grandchild.id).status == "cancelled"
        snap = orch.snapshot()
        assert child.id not in snap["pending_ids"]
        assert grandchild.id not in snap["pending_ids"]
        blocker.set()
        time.sleep(0.15)
        assert not child_ran.is_set()
        assert not grandchild_ran.is_set()

    def test_request_cancel_cancels_pending_auto_publish_upload_child(
        self,
        tmp_path: Path,
    ) -> None:
        store = JobStore.load(tmp_path)
        preview = store.create(tmp_path, job_type="preview", auto_publish=True)
        store.set_status(preview.id, "running", job_type="preview")
        upload = store.create(tmp_path, job_type="upload", parent_job_id=preview.id)
        assert upload.status == "pending"

        ids = store.request_cancel(preview.id)
        assert upload.id in ids
        assert store.get(upload.id).status == "cancelled"

    def test_set_preview_and_mark_done_do_not_overwrite_cancelled(
        self,
        tmp_path: Path,
    ) -> None:
        store = JobStore.load(tmp_path)
        preview_job = store.create(tmp_path)
        store.request_cancel(preview_job.id)
        store.set_preview(preview_job.id, _preview())
        assert store.get(preview_job.id).status == "cancelled"

        upload = store.create(tmp_path, job_type="upload")
        store.set_status(upload.id, "running", job_type="upload")
        store.request_cancel(upload.id)
        store.mark_done(upload.id, "https://photos.example/nope")
        assert store.get(upload.id).status == "cancelled"
        assert store.get(upload.id).product_url is None

    def test_cancel_running_scrape_stops_and_cancels_preview_child(
        self,
        tmp_path: Path,
    ) -> None:
        hold = threading.Event()
        started = threading.Event()
        fake = FakeAlbumScraper(hold=hold, started=started)
        service, store, bus = _scrape_service(tmp_path, scraper=fake)
        cancel = CancelService(store=store, events=bus)

        job_id = service.start("https://albums.example/day1")
        preview_id = store.list_children(job_id)[0].id
        thread = threading.Thread(target=service.finish, args=(job_id,), daemon=True)
        thread.start()
        try:
            assert started.wait(timeout=2)
            cancel.cancel(job_id)
            assert store.get(job_id).status == "cancelled"
            assert store.get(preview_id).status == "cancelled"
        finally:
            hold.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert store.get(job_id).status == "cancelled"
        assert store.get(preview_id).status == "cancelled"
        assert store.get(preview_id).preview is None
        stages = [event.stage for event in store.get(job_id).events]
        assert "cancelled" in stages
        assert "done" not in stages
        assert fake.calls  # scrape started before cancel stopped it

    def test_cancel_scrape_parent_does_not_spawn_further_child_scrapes(
        self,
        tmp_path: Path,
    ) -> None:
        hold = threading.Event()
        started = threading.Event()
        child_url = "https://albums.example/day2"
        fake = FakeAlbumScraper(
            files=[("index.html", b"<html>parent</html>", None)],
            gallery_urls=[child_url],
            hold=hold,
            started=started,
            by_url={child_url: FakeAlbumScraper(files=mini_album_files())},
        )
        service, store, bus = _scrape_service(tmp_path, scraper=fake)
        cancel = CancelService(store=store, events=bus)

        parent_id = service.start("https://albums.example/index")
        thread = threading.Thread(target=service.finish, args=(parent_id,), daemon=True)
        thread.start()
        try:
            assert started.wait(timeout=2)
            cancel.cancel(parent_id)
        finally:
            hold.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        children = store.list_children(parent_id)
        assert all(job.type != "scrape" or job.status == "cancelled" for job in children)
        assert not any(
            job.scrape_url == child_url and job.status == "done" for job in store.list()
        )
        assert store.get(parent_id).status == "cancelled"

    def test_cancel_mid_publish_marks_cancelled_not_done(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        preview_job = store.create(tmp_path)
        store.set_preview(preview_job.id, _preview())
        (preview_job.root / "hrimages").mkdir(parents=True, exist_ok=True)
        (preview_job.root / "hrimages" / "20120802_01hr.JPG").write_bytes(b"\xff\xd8\xff\xd9")
        (preview_job.root / "hrimages" / "20120802_02hr.JPG").write_bytes(b"\xff\xd8\xff\xd9")

        hold = threading.Event()
        started = threading.Event()

        class HoldingPublisher:
            def publish(
                self,
                gp: Any,
                root: Path,
                preview: AlbumPreview,
                sink: Any = None,
            ) -> Any:
                started.set()
                while not hold.wait(timeout=0.05):
                    raise_if_cancelled(sink)
                raise_if_cancelled(sink)
                album = MagicMock()
                album.productUrl = "https://photos.example/should-not-finish"
                return album

        events = JobEventBus(persist=store.append_event)
        service = PublishService(
            store=store,
            publisher=HoldingPublisher(),
            events=events,
            gp_factory=MagicMock(return_value=MagicMock()),
        )
        cancel = CancelService(store=store, events=events)
        upload_id = service.start(preview_job.id, access_token="ya29.tok")
        thread = threading.Thread(
            target=lambda: service.finish(upload_id, access_token="ya29.tok"),
            daemon=True,
        )
        thread.start()
        try:
            assert started.wait(timeout=2)
            cancel.cancel(upload_id)
        finally:
            hold.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        upload = store.get(upload_id)
        assert upload.status == "cancelled"
        assert upload.product_url is None
        stages = [event.stage for event in upload.events]
        assert "cancelled" in stages
        assert "done" not in stages

    def test_cancel_ingest_during_parse(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        events = JobEventBus(persist=store.append_event)
        hold = threading.Event()
        started = threading.Event()
        real = AlbumExportParser()

        class HoldingParser:
            def parse(
                self,
                root: Path,
                sink: Any = None,
                *,
                allow_loose_media: bool = False,
            ) -> AlbumPreview:
                started.set()
                while not hold.wait(timeout=0.05):
                    raise_if_cancelled(sink)
                raise_if_cancelled(sink)
                return real.parse(
                    root, sink=sink, allow_loose_media=allow_loose_media
                )

        service = IngestService(
            store=store,
            parser=HoldingParser(),
            events=events,
            workspace=JobWorkspace,
        )
        cancel = CancelService(store=store, events=events)
        result: dict[str, str] = {}

        def run() -> None:
            result["id"] = service.ingest(_mini_files(), jobs_root=tmp_path)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            assert started.wait(timeout=2)
            job = store.list()[0]
            cancel.cancel(job.id)
        finally:
            hold.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        job = store.get(result["id"])
        assert job.status == "cancelled"
        assert job.preview is None
        assert "cancelled" in [event.stage for event in job.events]
        assert "preview_ready" not in [event.stage for event in job.events]

    def test_post_cancel_running_scrape_is_200(self, tmp_path: Path) -> None:
        hold = threading.Event()
        started = threading.Event()
        client = _api_client(
            tmp_path, scraper=FakeAlbumScraper(hold=hold, started=started)
        )
        try:
            created = client.post(
                "/api/jobs/scrape",
                json={"url": "https://albums.example/day1"},
            )
            assert created.status_code == 201, created.text
            job_id = created.json()["id"]
            preview_id = created.json()["preview_job_id"]
            assert started.wait(timeout=2)
            response = client.post(f"/api/jobs/{job_id}/cancel")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["id"] == job_id
            assert body["status"] == "cancelled"
            assert body["type"] == "scrape"
            child = client.get(f"/api/jobs/{preview_id}").json()
            assert child["status"] == "cancelled"
        finally:
            hold.set()

    def test_post_cancel_done_job_is_409(self, tmp_path: Path) -> None:
        client = _api_client(tmp_path)
        created = client.post(
            "/api/jobs/scrape",
            json={"url": "https://albums.example/day1"},
        ).json()
        deadline_ok = False
        import time

        for _ in range(100):
            job = client.get(f"/api/jobs/{created['id']}").json()
            if job["status"] == "done":
                deadline_ok = True
                break
            time.sleep(0.05)
        assert deadline_ok
        response = client.post(f"/api/jobs/{created['id']}/cancel")
        assert response.status_code == 409
        assert client.get(f"/api/jobs/{created['id']}").json()["status"] == "done"

    def test_post_cancel_missing_job_is_404(self, tmp_path: Path) -> None:
        client = _api_client(tmp_path)
        assert client.post("/api/jobs/missing/cancel").status_code == 404

    def test_get_cancel_preview_lists_non_terminal_descendants(self, tmp_path: Path) -> None:
        from src.api.app import create_app

        app = create_app(jobs_root=tmp_path / "jobs")
        store = app.state.deps.store
        parent = store.create(tmp_path / "jobs", job_type="scrape")
        store.set_status(parent.id, "running", job_type="scrape")
        pending_child = store.create(
            tmp_path / "jobs", job_type="scrape", parent_job_id=parent.id
        )
        running_preview = store.create(
            tmp_path / "jobs", job_type="preview", parent_job_id=pending_child.id
        )
        store.set_status(running_preview.id, "running", job_type="preview")
        done_preview = store.create(
            tmp_path / "jobs", job_type="preview", parent_job_id=pending_child.id
        )
        store.set_preview(done_preview.id, _preview(title="Done preview"))

        client = TestClient(app)
        response = client.get(f"/api/jobs/{parent.id}/cancel-preview")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["job"]["id"] == parent.id
        descendant_ids = [row["id"] for row in body["descendants"]]
        assert pending_child.id in descendant_ids
        assert running_preview.id in descendant_ids
        assert done_preview.id not in descendant_ids
        assert parent.id not in descendant_ids
        by_id = {row["id"]: row for row in body["descendants"]}
        assert by_id[pending_child.id]["status"] == "pending"
        assert by_id[running_preview.id]["status"] == "running"
        assert by_id[running_preview.id]["parent_job_id"] == pending_child.id

    def test_get_cancel_preview_missing_is_404(self, tmp_path: Path) -> None:
        client = _api_client(tmp_path)
        assert client.get("/api/jobs/missing/cancel-preview").status_code == 404

    def test_post_cancel_pending_upload_via_store(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path, job_type="upload")
        assert job.status == "pending"
        events = JobEventBus(persist=store.append_event)
        CancelService(store=store, events=events).cancel(job.id)
        assert store.get(job.id).status == "cancelled"
        assert [event.stage for event in store.get(job.id).events][-1] == "cancelled"

