"""TDD: orchestrator settings API and queued ingest/publish."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from tests.support.album import AlbumTree
from tests.support.fakes.scraper import FakeAlbumScraper
from tests.support.suites import ScrapeFakeSuite
from tests.support.waits import JobWaiter


class TestOrchestratorSettingsApi(ScrapeFakeSuite):
    @pytest.fixture(autouse=True)
    def _bind_settings_api(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.make_api()

    def test_get_settings_default_cap(self) -> None:
        from src.jobs.orchestrator import DEFAULT_MAX_CONCURRENT

        client = self.client
        response = client.get("/api/settings")
        assert response.status_code == 200, response.text
        body = response.json()
        assert DEFAULT_MAX_CONCURRENT == 3
        assert body["max_concurrent_jobs"] == DEFAULT_MAX_CONCURRENT
        assert body["pending"] == 0
        assert body["running"] == 0
        assert body["waiting"] == 0

    def test_patch_settings_persists_across_app_reload(self, tmp_path: Path) -> None:
        client = self.make_api(tmp_path, with_scraper=True).client
        patched = client.patch("/api/settings", json={"max_concurrent_jobs": 5})
        assert patched.status_code == 200, patched.text
        assert patched.json()["max_concurrent_jobs"] == 5

        client2 = self.make_api(tmp_path, with_scraper=True).client
        loaded = client2.get("/api/settings").json()
        assert loaded["max_concurrent_jobs"] == 5

    def test_patch_settings_rejects_invalid(self, tmp_path: Path) -> None:
        client = self.make_api(tmp_path, with_scraper=True).client
        assert client.patch(
            "/api/settings", json={"max_concurrent_jobs": 0}
        ).status_code == 400
        assert client.patch(
            "/api/settings", json={"max_concurrent_jobs": 99}
        ).status_code == 400

    def test_ingest_returns_pending_then_completes(self, tmp_path: Path) -> None:
        api = self.make_api(tmp_path, with_scraper=True)
        created = api.client.post("/api/jobs", files=AlbumTree.mini_multipart())
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["type"] == "preview"
        assert body["status"] in {"pending", "running", "done"}
        done = JobWaiter().http_status(api.client, body["id"], timeout=5)
        assert done["status"] == "done"
        assert done["preview"]["title"] == "2/8/2012 - mini fixture"

    def test_cap_one_queues_second_scrape(self, tmp_path: Path) -> None:
        hold_a = threading.Event()
        started_a = threading.Event()
        hold_b = threading.Event()
        started_b = threading.Event()
        scraper = FakeAlbumScraper(
            hold=hold_a,
            started=started_a,
            by_url={
                "https://albums.example/day2": FakeAlbumScraper(
                    hold=hold_b, started=started_b
                )
            },
        )
        client = self.make_api(tmp_path, scraper=scraper, with_scraper=True).client
        assert (
            client.patch("/api/settings", json={"max_concurrent_jobs": 1}).status_code
            == 200
        )

        first = client.post(
            "/api/jobs/scrape", json={"url": "https://albums.example/day1"}
        ).json()
        second = client.post(
            "/api/jobs/scrape", json={"url": "https://albums.example/day2"}
        ).json()
        assert started_a.wait(timeout=2)
        time.sleep(0.1)
        assert not started_b.is_set()
        settings = client.get("/api/settings").json()
        assert settings["running"] == 1
        assert settings["pending"] >= 1
        listed = client.get("/api/jobs").json()["jobs"]
        ids = {row["id"] for row in listed}
        assert first["id"] in ids
        assert second["id"] in ids
        second_row = next(row for row in listed if row["id"] == second["id"])
        assert second_row["status"] == "pending"
        hold_a.set()
        assert started_b.wait(timeout=3)
        hold_b.set()
