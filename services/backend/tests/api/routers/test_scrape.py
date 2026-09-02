"""TDD: scrape/import job HTTP API (TestClient)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.export.scrape.scraper import NotArlesGalleryError, ScrapeFetchError
from src.jobs.scrape import ERROR_FETCH_FAILED, ERROR_NOT_ARLES
from tests.support.api import MigratorApi
from tests.support.fakes.scraper import FakeAlbumScraper, mini_album_files
from tests.support.waits import JobWaiter
from tests.support.suites import ScrapeFakeSuite

_WAITER = JobWaiter()


def _client(
    tmp_path: Path,
    *,
    scraper: FakeAlbumScraper | None = None,
    publisher: Any = None,
    gp_factory: Any = None,
) -> TestClient:
    return MigratorApi(
        tmp_path,
        scraper=scraper or FakeAlbumScraper(),
        publisher=publisher,
        gp_factory=gp_factory,
        with_scraper=True,
        product_url="https://photos.example/scrape-album",
    ).client


def _wait_job(
    client: TestClient,
    job_id: str,
    *,
    status: str = "done",
    timeout: float = 5.0,
) -> dict:
    return _WAITER.http_status(client, job_id, status=status, timeout=timeout)

class TestScrapeApi(ScrapeFakeSuite):
    def test_create_app_exposes_scrape_routes(self) -> None:
        from src.api.app import create_app

        paths = create_app().openapi().get("paths") or {}
        methods_by_path = {
            path: {method.upper() for method in operations}
            for path, operations in paths.items()
        }
        assert "POST" in methods_by_path["/api/jobs/scrape"]
        assert "GET" in methods_by_path["/api/jobs/{job_id}/children"]
        assert "GET" in methods_by_path["/api/jobs/{job_id}/cancel-preview"]
        assert "GET" in methods_by_path["/api/jobs/{job_id}/restart-preview"]

    def test_post_scrape_returns_running_job_then_spawns_preview_child(
        self,
        tmp_path: Path,
    ) -> None:
        hold = threading.Event()
        client = _client(tmp_path, scraper=FakeAlbumScraper(hold=hold))
        try:
            response = client.post(
                "/api/jobs/scrape",
                json={
                    "url": "https://albums.example/day1",
                    "headers": {"Cookie": "secret=1", "Authorization": "Bearer tok"},
                },
            )
            assert response.status_code == 201, response.text
            body = response.json()
            assert body["type"] == "scrape"
            assert body["status"] in {"pending", "running"}
            assert body["import_origin"] == "web"
            assert body["scrape_url"] == "https://albums.example/day1"
            assert body["has_headers"] is True
            assert body["header_names"] == ["Cookie", "Authorization"]
            assert "secret=1" not in response.text
            assert "Bearer tok" not in response.text
            assert "scrape_headers" not in body
            assert body["child_ids"]
            child_id = body["child_ids"][0]
            assert body["preview_job_id"] == child_id

            early = client.get(f"/api/jobs/{child_id}").json()
            assert early["type"] == "preview"
            assert early["status"] in {"pending", "running"}
            assert early["import_origin"] == "web"
            assert early["parent_job_id"] == body["id"]
            assert early["preview"] is None
        finally:
            hold.set()
        done = _wait_job(client, body["id"])
        assert done["status"] == "done"
        assert done["type"] == "scrape"
        assert done["preview"] is None
        assert done["child_ids"] == [child_id]
        assert done["preview_job_id"] == child_id

        child = client.get(f"/api/jobs/{child_id}").json()
        assert child["type"] == "preview"
        assert child["status"] == "done"
        assert child["import_origin"] == "web"
        assert child["parent_job_id"] == body["id"]
        assert child["preview"]["title"] == "2/8/2012 - mini fixture"

        children = client.get(f"/api/jobs/{body['id']}/children")
        assert children.status_code == 200, children.text
        listed = children.json()["jobs"]
        assert [row["id"] for row in listed] == [child_id]
        assert listed[0]["type"] == "preview"
        assert listed[0]["title"] == "2/8/2012 - mini fixture"
        assert listed[0]["parent_job_id"] == body["id"]
        assert listed[0]["import_origin"] == "web"

    def test_list_jobs_includes_scrape_runs_and_dedupe_by_url(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        first = client.post(
            "/api/jobs/scrape",
            json={"url": "https://albums.example/day1"},
        ).json()
        _wait_job(client, first["id"])
        second = client.post(
            "/api/jobs/scrape",
            json={"url": "https://albums.example/day1"},
        ).json()
        _wait_job(client, second["id"])

        listed = client.get("/api/jobs").json()["jobs"]
        scrape_ids = {row["id"] for row in listed if row["type"] == "scrape"}
        assert scrape_ids == {first["id"], second["id"]}
        preview_rows = [row for row in listed if row["type"] == "preview"]
        assert preview_rows
        first_row = next(row for row in listed if row["id"] == first["id"])
        second_row = next(row for row in listed if row["id"] == second["id"])
        assert first_row["title"] is None
        assert second_row["title"] is None
        assert first_row["preview_job_id"]
        assert second_row["preview_job_id"]
        assert first_row["preview_job_id"] != first["id"]
        assert second_row["preview_job_id"] != second["id"]
        first_preview = client.get(f"/api/jobs/{first_row['preview_job_id']}").json()
        assert first_preview["type"] == "preview"
        assert first_preview["parent_job_id"] == first["id"]

        albums = client.get("/api/jobs?dedupe=true").json()["jobs"]
        assert all(row["type"] != "scrape" for row in albums)
        assert {row["title"] for row in albums} == {"2/8/2012 - mini fixture"}
        assert all(row["type"] == "preview" for row in albums)
        assert len(albums) == 1

    def test_scrape_hub_index_spawns_eight_scrape_children(self, tmp_path: Path) -> None:
        child_urls = [
            f"https://albums.example/hub1/Day{index}/index.html"
            for index in range(1, 9)
        ]
        scraper = FakeAlbumScraper(
            files=(),
            gallery_urls=child_urls,
            by_url={
                url: FakeAlbumScraper(files=mini_album_files()) for url in child_urls
            },
        )
        client = _client(tmp_path, scraper=scraper)
        created = client.post(
            "/api/jobs/scrape",
            json={
                "url": "https://albums.example/hub1/index.html",
                "headers": {"Cookie": "session=abc"},
            },
        ).json()
        parent_id = created["id"]
        deadline = time.monotonic() + 8.0
        waiting_seen = False
        while time.monotonic() < deadline:
            body = client.get(f"/api/jobs/{parent_id}").json()
            if body.get("status") == "waiting":
                waiting_seen = True
                break
            if body.get("status") == "done":
                break
            time.sleep(0.02)
        if waiting_seen:
            children_during = client.get(f"/api/jobs/{parent_id}/children").json()["jobs"]
            assert any(row["status"] in {"pending", "running", "waiting"} for row in children_during)
        done = _wait_job(client, parent_id, timeout=15.0)
        assert done["status"] == "done"
        assert done["preview_job_id"] is None
        children = client.get(f"/api/jobs/{done['id']}/children").json()["jobs"]
        assert [row["type"] for row in children] == ["scrape"] * 8
        assert [row["scrape_url"] for row in children] == child_urls
        for row in children:
            _wait_job(client, row["id"], timeout=15.0)
        children = client.get(f"/api/jobs/{done['id']}/children").json()["jobs"]
        assert all(row["status"] == "done" for row in children)
        assert all(row.get("error") in (None, "") for row in children)

    def test_scrape_gallery_urls_appear_as_children(self, tmp_path: Path) -> None:
        scraper = FakeAlbumScraper(
            files=mini_album_files(),
            gallery_urls=["https://albums.example/day2"],
            by_url={
                "https://albums.example/day2": FakeAlbumScraper(files=mini_album_files())
            },
        )
        client = _client(tmp_path, scraper=scraper)
        created = client.post(
            "/api/jobs/scrape",
            json={"url": "https://albums.example/index"},
        ).json()
        done = _wait_job(client, created["id"])
        children = client.get(f"/api/jobs/{done['id']}/children").json()["jobs"]
        types = sorted(row["type"] for row in children)
        assert "preview" in types
        assert "scrape" in types
        child_scrape = next(row for row in children if row["type"] == "scrape")
        assert child_scrape["scrape_url"] == "https://albums.example/day2"
        assert child_scrape["parent_job_id"] == done["id"]
        child_scrape = _wait_job(client, child_scrape["id"])
        assert child_scrape["preview_job_id"]
        grand = client.get(f"/api/jobs/{child_scrape['id']}/children").json()["jobs"]
        assert [row["type"] for row in grand] == ["preview"]
        assert child_scrape["preview_job_id"] == grand[0]["id"]

    def test_preview_child_history_during_scrape(self, tmp_path: Path) -> None:
        hold = threading.Event()
        started = threading.Event()
        client = _client(
            tmp_path, scraper=FakeAlbumScraper(hold=hold, started=started)
        )
        try:
            response = client.post(
                "/api/jobs/scrape",
                json={"url": "https://albums.example/day1"},
            )
            assert response.status_code == 201, response.text
            body = response.json()
            child_id = body["preview_job_id"]
            assert started.wait(timeout=2)
            history = client.get(f"/api/jobs/{child_id}/history").json()["events"]
            stages = [event["stage"] for event in history]
            assert "scrape" in stages
            assert "preview_ready" not in stages
            assert any(
                "Fetching gallery index" in (event.get("message") or "")
                for event in history
            )
            parent_history = client.get(f"/api/jobs/{body['id']}/history").json()[
                "events"
            ]
            assert any(
                "Fetching gallery index" in (event.get("message") or "")
                for event in parent_history
            )
        finally:
            hold.set()
        _wait_job(client, body["id"])
        done_history = client.get(f"/api/jobs/{child_id}/history").json()["events"]
        assert any(event["stage"] == "scrape" for event in done_history)
        assert any(event["stage"] == "preview_ready" for event in done_history)

    def test_scrape_sse_emits_scrape_child_preview_ready_done(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        job_id = client.post(
            "/api/jobs/scrape",
            json={"url": "https://albums.example/day1"},
        ).json()["id"]
        stages = []
        with client.stream("GET", f"/api/jobs/{job_id}/events?phase=scrape") as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = json.loads(line[len("data:") :].strip())
                stages.append(payload["stage"])
                assert "secret" not in json.dumps(payload)
                if payload["stage"] in {"done", "error"}:
                    break
        assert "scrape" in stages
        assert "child" in stages
        assert "preview_ready" in stages
        assert stages[-1] == "done"

    def test_scrape_failure_is_201_then_failed(self, tmp_path: Path) -> None:
        client = _client(tmp_path, scraper=FakeAlbumScraper(error=RuntimeError("boom")))
        response = client.post(
            "/api/jobs/scrape",
            json={"url": "https://albums.example/day1"},
        )
        assert response.status_code == 201, response.text
        failed = _wait_job(client, response.json()["id"], status="failed")
        assert failed["type"] == "scrape"
        assert "boom" in (failed["error"] or "")
        assert failed.get("error_code") in (None, "")

    def test_scrape_unknown_html_is_failed_not_arles(self, tmp_path: Path) -> None:
        url = "https://albums.example/album/index2012.html"
        client = _client(
            tmp_path,
            scraper=FakeAlbumScraper(
                error=NotArlesGalleryError(f"Not a supported Arles album: {url}", url=url)
            ),
        )
        response = client.post("/api/jobs/scrape", json={"url": url})
        assert response.status_code == 201, response.text
        failed = _wait_job(client, response.json()["id"], status="failed")
        assert failed["status"] == "failed"
        assert failed["error_code"] == ERROR_NOT_ARLES
        blob = (failed["error"] or "").lower()
        assert "arles" in blob or "unsupported" in blob
        assert failed["status"] != "waiting"
        assert failed.get("preview_job_id") is None
        assert all(
            client.get(f"/api/jobs/{cid}").json().get("type") != "preview"
            for cid in failed.get("child_ids") or []
        )
        children = client.get(f"/api/jobs/{failed['id']}/children").json()["jobs"]
        assert children == []
        assert all(row.get("type") != "preview" for row in children)

    def test_scrape_fetch_404_is_failed_fetch_failed(self, tmp_path: Path) -> None:
        url = "https://albums.example/missing/index.html"
        client = _client(
            tmp_path,
            scraper=FakeAlbumScraper(
                error=ScrapeFetchError(
                    f"Failed to fetch gallery index: {url} (HTTP 404)",
                    url=url,
                    status_code=404,
                )
            ),
        )
        response = client.post("/api/jobs/scrape", json={"url": url})
        assert response.status_code == 201, response.text
        failed = _wait_job(client, response.json()["id"], status="failed")
        assert failed["error_code"] == ERROR_FETCH_FAILED
        assert "404" in (failed["error"] or "")
        assert failed.get("preview_job_id") is None
        children = client.get(f"/api/jobs/{failed['id']}/children").json()["jobs"]
        assert all(row.get("type") != "preview" for row in children)
        listed = client.get("/api/jobs").json()["jobs"]
        row = next(item for item in listed if item["id"] == failed["id"])
        assert row["error_code"] == ERROR_FETCH_FAILED

    def test_scrape_invalid_url_is_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        response = client.post("/api/jobs/scrape", json={"url": "not-a-url"})
        assert response.status_code == 400

    def test_get_children_missing_job_is_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        assert client.get("/api/jobs/nope/children").status_code == 404

    def test_scrape_auto_publish_creates_preview_and_upload_children(
        self,
        tmp_path: Path,
    ) -> None:
        publisher = MagicMock()
        album = MagicMock()
        album.productUrl = "https://photos.example/scrape-auto"
        publisher.publish.return_value = album
        gp_factory = MagicMock(return_value=MagicMock())
        client = _client(tmp_path, publisher=publisher, gp_factory=gp_factory)

        created = client.post(
            "/api/jobs/scrape",
            json={
                "url": "https://albums.example/day1",
                "auto_publish": True,
                "access_token": "ya29.scrape-token",
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["type"] == "scrape"
        assert body["auto_publish"] is True
        done = _wait_job(client, body["id"])
        children = client.get(f"/api/jobs/{done['id']}/children").json()["jobs"]
        types = {row["type"] for row in children}
        assert "preview" in types
        assert "upload" in types
        preview = next(row for row in children if row["type"] == "preview")
        upload = next(row for row in children if row["type"] == "upload")
        assert preview["parent_job_id"] == done["id"]
        assert upload["parent_job_id"] == done["id"]
        uploaded = _wait_job(client, upload["id"])
        assert uploaded["product_url"] == "https://photos.example/scrape-auto"
        gp_factory.assert_called_with("ya29.scrape-token")
        publisher.publish.assert_called()
        db_path = tmp_path / "jobs" / "migrator.sqlite"
        assert b"ya29.scrape-token" not in db_path.read_bytes()

    def test_scrape_auto_publish_skipped_when_cancelled_before_preview(
        self,
        tmp_path: Path,
    ) -> None:
        hold = threading.Event()
        started = threading.Event()
        publisher = MagicMock()
        client = _client(
            tmp_path,
            scraper=FakeAlbumScraper(hold=hold, started=started),
            publisher=publisher,
            gp_factory=MagicMock(return_value=MagicMock()),
        )
        try:
            response = client.post(
                "/api/jobs/scrape",
                json={
                    "url": "https://albums.example/day1",
                    "auto_publish": True,
                    "access_token": "ya29.cancelled",
                },
            )
            assert response.status_code == 201, response.text
            body = response.json()
            assert started.wait(timeout=2)
            cancel = client.post(f"/api/jobs/{body['id']}/cancel")
            assert cancel.status_code == 200, cancel.text
        finally:
            hold.set()
        cancelled = _wait_job(client, body["id"], status="cancelled")
        assert cancelled["auto_publish"] is True
        children = client.get(f"/api/jobs/{cancelled['id']}/children").json()["jobs"]
        assert not any(row["type"] == "upload" for row in children)
        publisher.publish.assert_not_called()

    def test_scrape_auto_publish_skipped_when_scrape_fails(
        self,
        tmp_path: Path,
    ) -> None:
        publisher = MagicMock()
        client = _client(
            tmp_path,
            scraper=FakeAlbumScraper(error=RuntimeError("boom")),
            publisher=publisher,
        )
        response = client.post(
            "/api/jobs/scrape",
            json={
                "url": "https://albums.example/day1",
                "auto_publish": True,
                "access_token": "ya29.fail-token",
            },
        )
        assert response.status_code == 201, response.text
        failed = _wait_job(client, response.json()["id"], status="failed")
        children = client.get(f"/api/jobs/{failed['id']}/children").json()["jobs"]
        assert not any(row["type"] == "upload" for row in children)
        publisher.publish.assert_not_called()

    def test_scrape_auto_publish_without_token_is_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        response = client.post(
            "/api/jobs/scrape",
            json={"url": "https://albums.example/day1", "auto_publish": True},
        )
        assert response.status_code == 400
        assert "token" in response.text.lower()

    def test_reprocess_web_preview_child_retries_scrape_and_keeps_preview_id(
        self,
        tmp_path: Path,
    ) -> None:
        scraper = FakeAlbumScraper()
        client = _client(tmp_path, scraper=scraper)
        created = client.post(
            "/api/jobs/scrape",
            json={
                "url": "https://albums.example/day1",
                "headers": {"Cookie": "retry-me"},
            },
        ).json()
        done = _wait_job(client, created["id"])
        preview_id = done["preview_job_id"]
        assert preview_id
        preview = client.get(f"/api/jobs/{preview_id}").json()
        assert preview["parent_job_id"] == created["id"]
        assert preview.get("import_origin") in (None, "web") or preview["parent_job_id"]
        client.patch(f"/api/jobs/{preview_id}", json={"title": "Edited title"})
        assert client.get(f"/api/jobs/{preview_id}").json()["preview"]["title"] == (
            "Edited title"
        )

        scraper.calls.clear()
        response = client.post(f"/api/jobs/{preview_id}/reprocess")
        assert response.status_code == 200, response.text
        assert response.json()["id"] == preview_id

        refreshed = _wait_job(client, preview_id)
        assert refreshed["id"] == preview_id
        assert refreshed["status"] == "done"
        assert refreshed["type"] == "preview"
        assert refreshed["preview"]["title"] == "2/8/2012 - mini fixture"
        assert scraper.calls
        assert scraper.calls[0]["url"] == "https://albums.example/day1"
        assert scraper.calls[0]["header_names"] == ["Cookie"]
        assert "retry-me" not in response.text

        scrape_done = _wait_job(client, created["id"])
        children = client.get(f"/api/jobs/{scrape_done['id']}/children").json()["jobs"]
        assert [row["id"] for row in children if row["type"] == "preview"] == [preview_id]

    def test_reprocess_hub_leaf_preview_retries_leaf_not_hub(self, tmp_path: Path) -> None:
        child_url = "https://albums.example/day1"
        hub_url = "https://albums.example/hub/index.html"
        leaf_scraper = FakeAlbumScraper(files=mini_album_files())
        scraper = FakeAlbumScraper(
            files=(),
            gallery_urls=[child_url],
            by_url={child_url: leaf_scraper},
        )
        client = _client(tmp_path, scraper=scraper)
        hub = client.post("/api/jobs/scrape", json={"url": hub_url}).json()
        _wait_job(client, hub["id"], timeout=15.0)
        children = client.get(f"/api/jobs/{hub['id']}/children").json()["jobs"]
        leaf = next(row for row in children if row["type"] == "scrape")
        leaf_done = _wait_job(client, leaf["id"], timeout=15.0)
        preview_id = leaf_done["preview_job_id"]
        assert preview_id

        scraper.calls.clear()
        leaf_scraper.calls.clear()
        response = client.post(f"/api/jobs/{preview_id}/reprocess")
        assert response.status_code == 200, response.text
        assert response.json()["id"] == preview_id
        refreshed = _wait_job(client, preview_id, timeout=15.0)
        assert refreshed["id"] == preview_id
        assert refreshed["status"] == "done"
        assert refreshed["preview"]["title"] == "2/8/2012 - mini fixture"
        assert any(call["url"] == child_url for call in scraper.calls)
        assert not any(call["url"] == hub_url for call in scraper.calls)

    def test_reprocess_web_new_mode_does_not_mutate_original_preview(
        self,
        tmp_path: Path,
    ) -> None:
        scraper = FakeAlbumScraper()
        client = _client(tmp_path, scraper=scraper)
        created = client.post(
            "/api/jobs/scrape",
            json={
                "url": "https://albums.example/day1",
                "headers": {"Cookie": "retry-me"},
            },
        ).json()
        done = _wait_job(client, created["id"])
        preview_id = done["preview_job_id"]
        assert preview_id
        client.patch(f"/api/jobs/{preview_id}", json={"title": "Edited title"})
        original = client.get(f"/api/jobs/{preview_id}").json()
        assert original["preview"]["title"] == "Edited title"
        assert original["user_edited"] is True
        original_caption = original["preview"]["items"][0]["caption"]

        scraper.calls.clear()
        response = client.post(
            f"/api/jobs/{preview_id}/reprocess",
            json={"mode": "new", "title_prefix": "Reprocessed · "},
        )
        assert response.status_code == 200, response.text
        new_id = response.json()["id"]
        assert new_id != preview_id
        deadline = time.monotonic() + 8.0
        new_job = None
        while time.monotonic() < deadline:
            latest = client.get(f"/api/jobs/{new_id}")
            if latest.status_code == 200:
                body = latest.json()
                title = ((body.get("preview") or {}).get("title") or "")
                if body.get("status") == "done" and title.startswith("Reprocessed · "):
                    new_job = body
                    break
            time.sleep(0.02)
        assert new_job is not None, f"new preview {new_id} did not get a prefixed title"
        assert new_job["id"] == new_id
        assert new_job["status"] == "done"
        assert new_job["type"] == "preview"
        assert new_job["preview"]["title"] == "Reprocessed · Edited title"
        assert new_job["user_edited"] is False
        assert scraper.calls
        assert scraper.calls[0]["url"] == "https://albums.example/day1"

        kept = client.get(f"/api/jobs/{preview_id}").json()
        assert kept["id"] == preview_id
        assert kept["preview"]["title"] == "Edited title"
        assert kept["preview"]["items"][0]["caption"] == original_caption
        assert kept["user_edited"] is True
        scrape_done = _wait_job(client, created["id"])
        children = client.get(f"/api/jobs/{scrape_done['id']}/children").json()["jobs"]
        assert [row["id"] for row in children if row["type"] == "preview"] == [preview_id]

    def test_reprocess_scrape_retries_with_stored_headers(self, tmp_path: Path) -> None:
        scraper = FakeAlbumScraper()
        client = _client(tmp_path, scraper=scraper)
        created = client.post(
            "/api/jobs/scrape",
            json={
                "url": "https://albums.example/day1",
                "headers": {"Cookie": "retry-me"},
            },
        ).json()
        _wait_job(client, created["id"])
        scraper.calls.clear()

        response = client.post(f"/api/jobs/{created['id']}/reprocess")
        assert response.status_code == 200, response.text
        assert response.json()["id"] == created["id"]
        body = _wait_job(client, created["id"])
        assert body["status"] == "done"
        assert body["type"] == "scrape"
        assert scraper.calls
        assert scraper.calls[0]["header_names"] == ["Cookie"]
        assert "retry-me" not in response.text

