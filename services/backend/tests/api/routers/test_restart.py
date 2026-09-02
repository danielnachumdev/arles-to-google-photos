"""TDD: restart a cancelled job as a new pending orchestrator run."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from tests.support.album import AlbumTree
from tests.support.api import MigratorApi
from tests.support.fakes.scraper import FakeAlbumScraper, mini_album_files
from tests.support.waits import JobWaiter
from tests.support.suites import ScrapeFakeSuite

_WAITER = JobWaiter()


def _mini_multipart() -> list:
    return AlbumTree.mini_multipart()


def _client(
    tmp_path: Path,
    *,
    scraper: FakeAlbumScraper | None = None,
    publisher: MagicMock | None = None,
    gp_factory: MagicMock | None = None,
) -> TestClient:
    return MigratorApi(
        tmp_path,
        scraper=scraper or FakeAlbumScraper(),
        publisher=publisher,
        gp_factory=gp_factory,
        with_scraper=True,
        product_url="https://photos.example/restart-album",
    ).client


def _wait_job(
    client: TestClient,
    job_id: str,
    *,
    status: str = "done",
    timeout: float = 8.0,
) -> dict:
    return _WAITER.http_status(client, job_id, status=status, timeout=timeout)






















def _cancelled_hub_with_children(
    tmp_path: Path,
    *,
    done_urls: list[str],
    remaining_urls: list[str],
    remaining_status: str = "failed",
    scraper: FakeAlbumScraper | None = None,
):
    gallery_urls = list(done_urls) + list(remaining_urls)
    album_scraper = scraper or FakeAlbumScraper(
        files=(),
        gallery_urls=gallery_urls,
        by_url={
            url: FakeAlbumScraper(files=mini_album_files()) for url in gallery_urls
        },
    )
    client = _client(tmp_path, scraper=album_scraper)
    store = client.app.state.deps.store
    hub = store.create(
        tmp_path / "jobs",
        job_type="scrape",
        scrape_url="https://albums.example/hub/index.html",
        scrape_headers={"Cookie": "session=abc"},
        folder_label="albums.example",
    )
    store.set_status(hub.id, "cancelled", job_type="scrape")
    done_ids = []
    for url in done_urls:
        child = store.create(
            tmp_path / "jobs",
            job_type="scrape",
            parent_job_id=hub.id,
            scrape_url=url,
        )
        store.set_status(child.id, "done", job_type="scrape")
        done_ids.append(child.id)
    remaining_ids = []
    for url in remaining_urls:
        child = store.create(
            tmp_path / "jobs",
            job_type="scrape",
            parent_job_id=hub.id,
            scrape_url=url,
        )
        store.set_status(child.id, remaining_status, job_type="scrape")
        remaining_ids.append(child.id)
    return client, album_scraper, hub, done_ids, remaining_ids

class TestRestartApi(ScrapeFakeSuite):
    def test_create_app_exposes_restart_route(self) -> None:
        from src.api.app import create_app

        paths = create_app().openapi().get("paths") or {}
        methods_by_path = {
            path: {method.upper() for method in operations}
            for path, operations in paths.items()
        }
        assert "POST" in methods_by_path["/api/jobs/{job_id}/restart"]
        assert "GET" in methods_by_path["/api/jobs/{job_id}/restart-preview"]

    def test_restart_cancelled_scrape_is_new_job(self, tmp_path: Path) -> None:
        hold = threading.Event()
        started = threading.Event()
        client = _client(
            tmp_path, scraper=FakeAlbumScraper(hold=hold, started=started)
        )
        created = client.post(
            "/api/jobs/scrape",
            json={
                "url": "https://albums.example/day1",
                "headers": {"Authorization": "Bearer tok", "Cookie": "secret=1"},
            },
        ).json()
        assert started.wait(timeout=2)
        cancelled = client.post(f"/api/jobs/{created['id']}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        hold.set()
        time.sleep(0.05)

        restarted = client.post(f"/api/jobs/{created['id']}/restart", json={})
        assert restarted.status_code == 201, restarted.text
        new_job = restarted.json()
        assert new_job["id"] != created["id"]
        assert new_job["number"] != created["number"]
        assert new_job["number"] >= 1
        assert new_job["type"] == "scrape"
        assert new_job["status"] in {"pending", "running", "done"}
        assert new_job["import_origin"] == "web"
        assert new_job["scrape_url"] == "https://albums.example/day1"
        assert new_job["has_headers"] is True
        assert new_job["header_names"] == ["Authorization", "Cookie"]
        assert "Bearer tok" not in restarted.text
        assert "secret=1" not in restarted.text
        assert new_job.get("parent_job_id") in (None, "")

        old = client.get(f"/api/jobs/{created['id']}").json()
        assert old["status"] == "cancelled"
        assert old["id"] == created["id"]
        assert old["number"] == created["number"]

        done = _wait_job(client, new_job["id"])
        assert done["status"] == "done"
        assert done["type"] == "scrape"
        assert client.get(f"/api/jobs/{created['id']}").json()["status"] == "cancelled"

    def test_restart_cancelled_hub_does_not_reuse_children(self, tmp_path: Path) -> None:
        child_urls = [
            "https://albums.example/hub/Day1/index.html",
            "https://albums.example/hub/Day2/index.html",
        ]
        hold = threading.Event()
        started = threading.Event()
        scraper = FakeAlbumScraper(
            files=(),
            gallery_urls=child_urls,
            hold=hold,
            started=started,
            by_url={
                url: FakeAlbumScraper(files=mini_album_files()) for url in child_urls
            },
        )
        client = _client(tmp_path, scraper=scraper)
        created = client.post(
            "/api/jobs/scrape",
            json={
                "url": "https://albums.example/hub/index.html",
                "headers": {"Cookie": "session=abc"},
            },
        ).json()
        assert started.wait(timeout=2)
        client.post(f"/api/jobs/{created['id']}/cancel")
        hold.set()
        time.sleep(0.1)
        old_children = client.get(f"/api/jobs/{created['id']}/children").json()["jobs"]
        old_child_ids = {row["id"] for row in old_children}

        restarted = client.post(f"/api/jobs/{created['id']}/restart", json={})
        assert restarted.status_code == 201, restarted.text
        new_id = restarted.json()["id"]
        assert new_id != created["id"]
        done = _wait_job(client, new_id, timeout=15.0)
        assert done["status"] == "done"
        assert client.get(f"/api/jobs/{created['id']}").json()["status"] == "cancelled"

        new_children = client.get(f"/api/jobs/{new_id}/children").json()["jobs"]
        new_child_ids = {row["id"] for row in new_children}
        assert old_child_ids.isdisjoint(new_child_ids)
        scrape_children = [row for row in new_children if row["type"] == "scrape"]
        assert [row["scrape_url"] for row in scrape_children] == child_urls
        for row in scrape_children:
            _wait_job(client, row["id"], timeout=15.0)
            assert row["id"] not in old_child_ids
            assert client.get(f"/api/jobs/{row['id']}").json()["parent_job_id"] == new_id

    def test_restart_non_cancelled_is_409(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        created = client.post(
            "/api/jobs/scrape", json={"url": "https://albums.example/day1"}
        ).json()
        done = _wait_job(client, created["id"])
        response = client.post(f"/api/jobs/{done['id']}/restart", json={})
        assert response.status_code == 409, response.text
        assert client.get(f"/api/jobs/{done['id']}").json()["id"] == done["id"]

    def test_restart_running_is_409(self, tmp_path: Path) -> None:
        hold = threading.Event()
        started = threading.Event()
        client = _client(
            tmp_path, scraper=FakeAlbumScraper(hold=hold, started=started)
        )
        try:
            created = client.post(
                "/api/jobs/scrape", json={"url": "https://albums.example/day1"}
            ).json()
            assert started.wait(timeout=2)
            response = client.post(f"/api/jobs/{created['id']}/restart", json={})
            assert response.status_code == 409, response.text
            assert client.get(f"/api/jobs/{created['id']}").json()["status"] == "running"
        finally:
            hold.set()

    def test_restart_missing_is_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        assert client.post("/api/jobs/nope/restart", json={}).status_code == 404

    def test_restart_cancelled_preview_parses_copied_artifacts(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        created = client.post("/api/jobs", files=_mini_multipart())
        assert created.status_code == 201, created.text
        done = _wait_job(client, created.json()["id"])
        job_id = done["id"]
        source_index = (tmp_path / "jobs" / job_id / "index.html").read_bytes()
        client.app.state.deps.store.set_status(job_id, "cancelled", job_type="preview")
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "cancelled"

        restarted = client.post(f"/api/jobs/{job_id}/restart", json={})
        assert restarted.status_code == 201, restarted.text
        new_job = restarted.json()
        assert new_job["id"] != job_id
        assert new_job["type"] == "preview"
        assert new_job["status"] in {"pending", "running", "done"}
        assert new_job["import_origin"] == "folder"
        assert new_job.get("folder_label") == done.get("folder_label")
        parsed = _wait_job(client, new_job["id"])
        assert parsed["status"] == "done"
        assert parsed["type"] == "preview"
        assert parsed["preview"]["title"] == "2/8/2012 - mini fixture"
        assert len(parsed["preview"]["items"]) == 1
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "cancelled"
        assert (tmp_path / "jobs" / job_id / "index.html").read_bytes() == source_index
        old_events = client.get(f"/api/jobs/{job_id}/history").json()["events"]
        new_events = client.get(f"/api/jobs/{new_job['id']}/history").json()["events"]
        assert old_events
        assert new_events
        assert [event["occurred_at"] for event in old_events] != [
            event["occurred_at"] for event in new_events
        ] or len(new_events) != len(old_events)

    def test_restart_cancelled_web_preview_keeps_web_origin(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        created = client.post(
            "/api/jobs/scrape", json={"url": "https://albums.example/day1"}
        ).json()
        done = _wait_job(client, created["id"])
        preview_id = done["preview_job_id"]
        preview = client.get(f"/api/jobs/{preview_id}").json()
        assert preview["type"] == "preview"
        assert preview["import_origin"] == "web"
        assert preview["parent_job_id"] == created["id"]
        client.app.state.deps.store.set_status(
            preview_id, "cancelled", job_type="preview"
        )

        restarted = client.post(f"/api/jobs/{preview_id}/restart", json={})
        assert restarted.status_code == 201, restarted.text
        new_job = restarted.json()
        assert new_job["id"] != preview_id
        assert new_job["type"] == "preview"
        assert new_job["import_origin"] == "web"
        assert new_job.get("parent_job_id") in (None, "")
        parsed = _wait_job(client, new_job["id"])
        assert parsed["status"] == "done"
        assert parsed["import_origin"] == "web"
        assert parsed.get("parent_job_id") in (None, "")
        assert client.get(f"/api/jobs/{preview_id}").json()["status"] == "cancelled"

    def test_restart_while_cap_full_stays_pending(self, tmp_path: Path) -> None:
        hold_a = threading.Event()
        started_a = threading.Event()
        client = _client(
            tmp_path,
            scraper=FakeAlbumScraper(hold=hold_a, started=started_a),
        )
        try:
            assert (
                client.patch("/api/settings", json={"max_concurrent_jobs": 1}).status_code
                == 200
            )
            first = client.post(
                "/api/jobs/scrape", json={"url": "https://albums.example/day1"}
            ).json()
            assert started_a.wait(timeout=2)

            other = client.post(
                "/api/jobs/scrape", json={"url": "https://albums.example/day2"}
            ).json()
            assert client.get(f"/api/jobs/{other['id']}").json()["status"] == "pending"
            cancelled = client.post(f"/api/jobs/{other['id']}/cancel")
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"

            restarted = client.post(f"/api/jobs/{other['id']}/restart", json={})
            assert restarted.status_code == 201, restarted.text
            new_job = restarted.json()
            assert new_job["id"] != other["id"]
            assert new_job["status"] == "pending"
            settings = client.get("/api/settings").json()
            assert settings["running"] == 1
            assert settings["pending"] >= 1
            listed = client.get("/api/jobs").json()["jobs"]
            new_row = next(row for row in listed if row["id"] == new_job["id"])
            assert new_row["status"] == "pending"
            old_row = next(row for row in listed if row["id"] == other["id"])
            assert old_row["status"] == "cancelled"
            assert client.get(f"/api/jobs/{first['id']}").json()["status"] == "running"
        finally:
            hold_a.set()

    def test_restart_cancelled_upload_requires_token(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        preview = client.post("/api/jobs", files=_mini_multipart())
        preview_id = preview.json()["id"]
        _wait_job(client, preview_id)
        published = client.post(
            f"/api/jobs/{preview_id}/publish",
            json={"access_token": "ya29.first"},
        )
        assert published.status_code == 201, published.text
        upload_id = published.json()["id"]
        _wait_job(client, upload_id)
        client.app.state.deps.store.set_status(upload_id, "cancelled", job_type="upload")

        missing = client.post(f"/api/jobs/{upload_id}/restart", json={})
        assert missing.status_code in {400, 401}

        restarted = client.post(
            f"/api/jobs/{upload_id}/restart",
            json={"access_token": "ya29.restart"},
        )
        assert restarted.status_code == 201, restarted.text
        new_job = restarted.json()
        assert new_job["id"] != upload_id
        assert new_job["type"] == "upload"
        assert new_job["status"] in {"pending", "running", "done"}
        done = _wait_job(client, new_job["id"])
        assert done["status"] == "done"
        assert done["product_url"]
        assert client.get(f"/api/jobs/{upload_id}").json()["status"] == "cancelled"

    def test_restart_preview_cancelled_hub_lists_done_vs_remaining(self, tmp_path: Path) -> None:
        done_urls = [
            "https://albums.example/hub/Day1/index.html",
            "https://albums.example/hub/Day2/index.html",
        ]
        remaining_url = "https://albums.example/hub/Day3/index.html"
        client, _scraper, hub, done_ids, remaining_ids = _cancelled_hub_with_children(
            tmp_path,
            done_urls=done_urls,
            remaining_urls=[remaining_url],
            remaining_status="failed",
        )
        preview_child = client.app.state.deps.store.create(
            tmp_path / "jobs",
            job_type="preview",
            parent_job_id=hub.id,
        )
        response = client.get(f"/api/jobs/{hub.id}/restart-preview")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["job"]["id"] == hub.id
        descendant_ids = [row["id"] for row in body["descendants"]]
        assert set(descendant_ids) == set(done_ids + remaining_ids)
        assert preview_child.id not in descendant_ids
        assert {row["id"] for row in body["done"]} == set(done_ids)
        assert {row["id"] for row in body["remaining"]} == set(remaining_ids)
        by_id = {row["id"]: row for row in body["descendants"]}
        assert by_id[done_ids[0]]["status"] == "done"
        assert by_id[remaining_ids[0]]["status"] == "failed"
        assert by_id[remaining_ids[0]]["scrape_url"] == remaining_url

    def test_restart_preview_leaf_scrape_omits_preview_child(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        store = client.app.state.deps.store
        leaf = store.create(
            tmp_path / "jobs",
            job_type="scrape",
            scrape_url="https://albums.example/day1",
        )
        store.set_status(leaf.id, "cancelled", job_type="scrape")
        preview = store.create(
            tmp_path / "jobs",
            job_type="preview",
            parent_job_id=leaf.id,
        )
        response = client.get(f"/api/jobs/{leaf.id}/restart-preview")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["job"]["id"] == leaf.id
        assert body["descendants"] == []
        assert body["done"] == []
        assert body["remaining"] == []
        assert preview.id not in [row["id"] for row in body["descendants"]]

    def test_restart_preview_non_cancelled_is_409(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        created = client.post(
            "/api/jobs/scrape", json={"url": "https://albums.example/day1"}
        ).json()
        done = _wait_job(client, created["id"])
        response = client.get(f"/api/jobs/{done['id']}/restart-preview")
        assert response.status_code == 409, response.text

    def test_restart_preview_missing_is_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        assert client.get("/api/jobs/nope/restart-preview").status_code == 404

    def test_restart_remaining_skips_done_child_urls(self, tmp_path: Path) -> None:
        done_urls = [
            "https://albums.example/hub/Day1/index.html",
            "https://albums.example/hub/Day2/index.html",
        ]
        remaining_url = "https://albums.example/hub/Day3/index.html"
        client, scraper, hub, done_ids, remaining_ids = _cancelled_hub_with_children(
            tmp_path,
            done_urls=done_urls,
            remaining_urls=[remaining_url],
            remaining_status="cancelled",
        )

        restarted = client.post(
            f"/api/jobs/{hub.id}/restart", json={"mode": "remaining"}
        )
        assert restarted.status_code == 201, restarted.text
        new_job = restarted.json()
        assert new_job["id"] != hub.id
        assert new_job["type"] == "scrape"
        extra = client.app.state.deps.store.get(new_job["id"]).extra or {}
        assert extra.get("restarted_from") == hub.id
        assert set(extra.get("skip_done_urls") or []) == set(done_urls)

        done = _wait_job(client, new_job["id"], timeout=15.0)
        assert done["status"] in {"done", "waiting"}
        assert client.get(f"/api/jobs/{hub.id}").json()["status"] == "cancelled"

        new_children = client.get(f"/api/jobs/{new_job['id']}/children").json()["jobs"]
        scrape_children = [row for row in new_children if row["type"] == "scrape"]
        assert [row["scrape_url"] for row in scrape_children] == [remaining_url]
        assert scrape_children[0]["id"] not in remaining_ids
        assert scrape_children[0]["id"] not in done_ids
        assert client.get(f"/api/jobs/{scrape_children[0]['id']}").json()[
            "parent_job_id"
        ] == new_job["id"]

        for done_id in done_ids:
            old = client.get(f"/api/jobs/{done_id}").json()
            assert old["id"] == done_id
            assert old["status"] == "done"
            assert old["parent_job_id"] == hub.id

        assert scraper.calls and scraper.calls[0]["url"] == hub.scrape_url
        assert not scraper.by_url[done_urls[0]].calls
        assert not scraper.by_url[done_urls[1]].calls
        assert scraper.by_url[remaining_url].calls
        _wait_job(client, scrape_children[0]["id"], timeout=15.0)

    def test_restart_remaining_with_nothing_left_is_400(self, tmp_path: Path) -> None:
        done_urls = [
            "https://albums.example/hub/Day1/index.html",
            "https://albums.example/hub/Day2/index.html",
        ]
        client, _scraper, hub, _done_ids, _remaining_ids = _cancelled_hub_with_children(
            tmp_path,
            done_urls=done_urls,
            remaining_urls=[],
        )
        before_ids = {row["id"] for row in client.get("/api/jobs").json()["jobs"]}
        response = client.post(
            f"/api/jobs/{hub.id}/restart", json={"mode": "remaining"}
        )
        assert response.status_code == 400, response.text
        assert "remaining" in response.text.lower()
        after_ids = {row["id"] for row in client.get("/api/jobs").json()["jobs"]}
        assert after_ids == before_ids

    def test_restart_leaf_mode_remaining_does_not_require_children(self, tmp_path: Path) -> None:
        client = _client(tmp_path, scraper=FakeAlbumScraper(files=mini_album_files()))
        created = client.post(
            "/api/jobs/scrape", json={"url": "https://albums.example/day1"}
        ).json()
        done = _wait_job(client, created["id"])
        preview_id = done["preview_job_id"]
        assert preview_id
        client.app.state.deps.store.set_status(
            created["id"], "cancelled", job_type="scrape"
        )

        restarted = client.post(
            f"/api/jobs/{created['id']}/restart", json={"mode": "remaining"}
        )
        assert restarted.status_code == 201, restarted.text
        new_job = restarted.json()
        assert new_job["id"] != created["id"]
        parsed = _wait_job(client, new_job["id"])
        assert parsed["status"] == "done"
        extra = client.app.state.deps.store.get(new_job["id"]).extra or {}
        assert extra.get("skip_done_urls") in (None, [])
        assert client.get(f"/api/jobs/{created['id']}").json()["status"] == "cancelled"
        assert client.get(f"/api/jobs/{preview_id}").json()["id"] == preview_id

