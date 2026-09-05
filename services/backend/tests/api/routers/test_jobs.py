"""TDD: thin FastAPI job API (TestClient)."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DAY1_MINI
from tests.support.album import AlbumTree
from tests.support.api import MigratorApi
from tests.support.waits import JobWaiter
from tests.support.suites import ApiClientSuite

_WAITER = JobWaiter()


def _mini_multipart() -> list:
    return AlbumTree.mini_multipart()


def _arles_multipart() -> list:
    return AlbumTree.arles_multipart()


def _api(
    tmp_path: Path,
    *,
    publisher: MagicMock | None = None,
    gp_factory: MagicMock | None = None,
    state_backend: str | None = None,
) -> MigratorApi:
    return MigratorApi(
        tmp_path,
        publisher=publisher,
        gp_factory=gp_factory,
        state_backend=state_backend,
    )


def _client(
    tmp_path: Path,
    *,
    publisher: MagicMock | None = None,
    gp_factory: MagicMock | None = None,
) -> TestClient:
    return _api(tmp_path, publisher=publisher, gp_factory=gp_factory).client


def _publish(client: TestClient, job_id: str, token: str = "ya29.test-token"):
    return client.post(
        f"/api/jobs/{job_id}/publish",
        json={"access_token": token},
    )


def _ingest(
    client: TestClient,
    files: list | None = None,
    *,
    overwrite: bool = False,
    auto_publish: bool = False,
    token: str | None = None,
    timeout: float = 8.0,
) -> dict:
    params: list[str] = []
    if overwrite:
        params.append("overwrite=true")
    if auto_publish:
        params.append("auto_publish=true")
    query = f"?{'&'.join(params)}" if params else ""
    data = {"access_token": token} if token else None
    response = client.post(
        f"/api/jobs{query}",
        files=files or _mini_multipart(),
        data=data,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    # Require a post-parse lifecycle stage so we never return between set_preview
    # (status=done) and emit(preview_ready). auto_publish may advance to "done".
    return _wait_job(
        client,
        body["id"],
        timeout=timeout,
        last_stages=("preview_ready", "done"),
    )


def _wait_job(
    client: TestClient,
    job_id: str,
    *,
    status: str = "done",
    last_stage: str | None = None,
    last_stages: tuple[str, ...] | set[str] | frozenset[str] | None = None,
    timeout: float = 5.0,
) -> dict:
    return _WAITER.http_status(
        client,
        job_id,
        status=status,
        last_stage=last_stage,
        last_stages=last_stages,
        timeout=timeout,
    )




















def _video_album_multipart() -> list:
    return AlbumTree.video_multipart()

class TestJobsApi(ApiClientSuite):
    def test_create_app_importable(self) -> None:
        from src.api.app import create_app

        assert create_app is not None

    def test_create_app_exposes_job_http_routes(self) -> None:
        from src.api.app import create_app

        paths = create_app().openapi().get("paths") or {}
        methods_by_path = {
            path: {method.upper() for method in operations}
            for path, operations in paths.items()
        }

        assert "POST" in methods_by_path["/api/jobs"]
        assert "GET" in methods_by_path["/api/jobs"]
        assert "GET" in methods_by_path["/api/jobs/{job_id}"]
        assert "DELETE" in methods_by_path["/api/jobs/{job_id}"]
        assert "PATCH" in methods_by_path["/api/jobs/{job_id}"]
        assert "GET" in methods_by_path["/api/jobs/{job_id}/media/{item_id}"]
        assert "POST" in methods_by_path["/api/jobs/{job_id}/publish"]
        assert "POST" in methods_by_path["/api/jobs/{job_id}/reprocess"]
        assert "POST" in methods_by_path["/api/jobs/{job_id}/restart"]
        assert "GET" in methods_by_path["/api/jobs/{job_id}/restart-preview"]
        assert "POST" in methods_by_path["/api/jobs/{job_id}/cancel"]
        assert "POST" in methods_by_path["/api/jobs/{job_id}/archive"]
        assert "GET" in methods_by_path["/api/jobs/{job_id}/events"]
        assert "GET" in methods_by_path["/api/jobs/{job_id}/history"]
        assert "GET" in methods_by_path["/api/jobs/{job_id}/children"]
        assert "GET" in methods_by_path["/api/jobs/{job_id}/cancel-preview"]
        assert "POST" in methods_by_path["/api/jobs/scrape"]
        assert "GET" in methods_by_path["/api/auth/config"]
        assert "GET" in methods_by_path["/api/settings"]
        assert "PATCH" in methods_by_path["/api/settings"]

    def test_post_job_parses_day1_mini(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        created = client.post("/api/jobs", files=_mini_multipart())
        assert created.status_code == 201, created.text
        assert created.json()["status"] in {"pending", "running", "done"}
        body = _wait_job(client, created.json()["id"])
        assert body["status"] == "done"
        assert body["type"] == "preview"
        assert body["import_origin"] == "folder"
        assert body["number"] == 1
        assert body["preview"]["title"] == "2/8/2012 - mini fixture"
        assert body["preview"]["description"] == "A tiny album used in unit tests"
        assert len(body["preview"]["items"]) == 1
        assert body["preview"]["items"][0]["id"] == "20120802_01"
        assert body["preview"]["items"][0]["caption"] == "כיתוב ראשון"
        assert body["preview"]["items"][0]["taken_on"] == "2012-08-02"
        assert body["preview"]["journal"] is None
        job_id = body["id"]

        got = client.get(f"/api/jobs/{job_id}")
        assert got.status_code == 200
        assert got.json()["id"] == job_id
        assert got.json()["number"] == 1

    def test_post_job_ndjson_streams_store_progress_on_cloud_path(
        self, tmp_path: Path
    ) -> None:
        """Local FS backend skips inline store events; still returns done + preview."""
        client = _client(tmp_path)
        created = client.post(
            "/api/jobs",
            files=_mini_multipart(),
            headers={"Accept": "application/x-ndjson"},
        )
        assert created.status_code == 201, created.text
        assert "application/x-ndjson" in (created.headers.get("content-type") or "")
        lines = [ln for ln in created.text.strip().splitlines() if ln.strip()]
        events = [json.loads(ln) for ln in lines]
        done = next(e for e in events if e.get("event") == "done")
        assert done["job"]["id"]
        body = _wait_job(client, done["job"]["id"])
        assert body["status"] == "done"
        assert body["preview"]["title"] == "2/8/2012 - mini fixture"

    def test_post_job_parses_day1_arles_journal_and_order(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        preview = _ingest(client, _arles_multipart())["preview"]
        assert preview["description"] is None
        assert preview["journal"]["heading"] == "יומן"
        assert preview["journal"]["paragraphs"][0].startswith("היום יצאנו")
        assert [item["id"] for item in preview["items"]] == ["20120802_02", "20120802_01"]
        assert preview["items"][0]["taken_on"] == "2012-08-02"

    def test_patch_journal(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        job_id = _ingest(client)["id"]
        response = client.patch(
            f"/api/jobs/{job_id}",
            json={"journal": {"heading": "New journal", "paragraphs": ["p1", "p2"]}},
        )
        assert response.status_code == 200, response.text
        journal = response.json()["preview"]["journal"]
        assert journal == {"heading": "New journal", "paragraphs": ["p1", "p2"]}

    def test_get_missing_job_is_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        assert client.get("/api/jobs/nope").status_code == 404

    def test_patch_edits_preview(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        job_id = _ingest(client)["id"]
        response = client.patch(
            f"/api/jobs/{job_id}",
            json={
                "title": "Edited title",
                "captions": {"20120802_01": "new caption"},
            },
        )
        assert response.status_code == 200, response.text
        preview = response.json()["preview"]
        assert preview["title"] == "Edited title"
        assert preview["items"][0]["caption"] == "new caption"
        assert response.json()["user_edited"] is True
        listed = client.get("/api/jobs").json()["jobs"]
        row = next(job for job in listed if job["id"] == job_id)
        assert row["user_edited"] is True

    def test_patch_noop_does_not_set_user_edited(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        created = _ingest(client)
        job_id = created["id"]
        assert created.get("user_edited") is False
        original_title = created["preview"]["title"]
        response = client.patch(f"/api/jobs/{job_id}", json={"title": original_title})
        assert response.status_code == 200, response.text
        assert response.json()["preview"]["title"] == original_title
        assert response.json()["user_edited"] is False

    def test_get_media_bytes(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        job_id = _ingest(client)["id"]
        response = client.get(f"/api/jobs/{job_id}/media/20120802_01")
        assert response.status_code == 200
        assert response.content == (DAY1_MINI / "hrimages" / "20120802_01hr.JPG").read_bytes()

    def test_get_media_variants_for_video_item(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        job = _ingest(client, _video_album_multipart())
        job_id = job["id"]
        item = job["preview"]["items"][0]
        assert item["id"] == "0512_1_06[1]"
        assert item["kind"] == "video"
        assert item["relpath"] == "hrimages/0512_1_06[1]hr.wmv"
        assert item["thumb_relpath"] == "thumbnails/TN_0512_1_06[1].jpg"
        assert item["play_relpath"] == "preview/0512_1_06[1].mp4"

        original = client.get(f"/api/jobs/{job_id}/media/0512_1_06[1]")
        assert original.status_code == 200
        assert original.content.startswith(b"WMV")

        same = client.get(f"/api/jobs/{job_id}/media/0512_1_06[1]?variant=original")
        assert same.status_code == 200
        assert same.content == original.content

        thumb = client.get(f"/api/jobs/{job_id}/media/0512_1_06[1]?variant=thumb")
        assert thumb.status_code == 200
        assert thumb.content.startswith(b"\xff\xd8")

        play = client.get(f"/api/jobs/{job_id}/media/0512_1_06[1]?variant=play")
        assert play.status_code == 200
        assert play.content == b"ftyp-fake-mp4"

        bad = client.get(f"/api/jobs/{job_id}/media/0512_1_06[1]?variant=nope")
        assert bad.status_code == 400

    def test_get_media_play_missing_returns_404(
        self,
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "src.jobs.ingest.ensure_local_video_previews",
            lambda root: None,
        )
        index = """<!DOCTYPE html>
    <html><body>
      <span class="gallerytitle">Bare video</span>
      <a href="imagepages/clip01.html"><img src="thumbnails/TN_clip01.jpg"></a>
    </body></html>
    """
        files = [
            ("files", ("index.html", index.encode("utf-8"), "text/html")),
            (
                "files",
                (
                    "imagepages/clip01.html",
                    b"<html><body></body></html>",
                    "text/html",
                ),
            ),
            ("files", ("hrimages/clip01hr.wmv", b"WMV-only", "video/x-ms-wmv")),
        ]
        client = _client(tmp_path)
        job = _ingest(client, files)
        item = job["preview"]["items"][0]
        assert item["kind"] == "video"
        assert item["play_relpath"] is None
        response = client.get(f"/api/jobs/{job['id']}/media/clip01?variant=play")
        assert response.status_code == 404
        thumb = client.get(f"/api/jobs/{job['id']}/media/clip01?variant=thumb")
        assert thumb.status_code == 404

    def test_get_job_history_after_ingest(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        job_id = _ingest(client)["id"]
        response = client.get(f"/api/jobs/{job_id}/history")
        assert response.status_code == 200, response.text
        events = response.json()["events"]
        stages = [event["stage"] for event in events]
        assert "ingest" in stages
        assert "preview_ready" in stages
        for event in events:
            assert event["occurred_at"]
            datetime.fromisoformat(str(event["occurred_at"]).replace("Z", "+00:00"))
            assert event["kind"] in {"log", "lifecycle"}
            assert event["audience"] in {"ui", "ops"}
        assert any(event["stage"] == "ingest" and event["kind"] == "log" for event in events)
        assert any(
            event["stage"] == "preview_ready" and event["kind"] == "lifecycle"
            for event in events
        )
        assert all(event["audience"] == "ui" for event in events)

    def test_get_job_history_survives_new_app(self, tmp_path: Path) -> None:
        client1 = _client(tmp_path)
        job_id = _ingest(client1)["id"]
        published = _publish(client1, job_id)
        assert published.status_code == 201, published.text
        upload_id = published.json()["id"]
        _wait_job(client1, upload_id)
        preview_events = client1.get(f"/api/jobs/{job_id}/history").json()["events"]
        assert not any(event["stage"] == "done" for event in preview_events)
        first = client1.get(f"/api/jobs/{upload_id}/history").json()["events"]
        assert any(event["stage"] == "done" for event in first)

        client2 = _client(tmp_path)
        second = client2.get(f"/api/jobs/{upload_id}/history").json()["events"]
        assert [event["stage"] for event in second] == [event["stage"] for event in first]
        assert [event["occurred_at"] for event in second] == [
            event["occurred_at"] for event in first
        ]

    def test_get_job_history_audience_filter(self, tmp_path: Path) -> None:
        from src.api.app import create_app

        publisher = MagicMock()
        album = MagicMock()
        album.productUrl = "https://photos.example/album-1"
        publisher.publish.return_value = album
        app = create_app(
            jobs_root=tmp_path / "jobs",
            gp_factory=MagicMock(return_value=MagicMock(name="GooglePhotos")),
            publisher=publisher,
        )
        client = TestClient(app)
        job_id = _ingest(client)["id"]
        app.state.deps.events.logger_for(job_id).ops(
            "GET https://albums.example/index.html → 200, 812KB",
            stage="scrape",
        )

        default = client.get(f"/api/jobs/{job_id}/history").json()["events"]
        assert any(event["stage"] == "preview_ready" for event in default)
        assert any(event["stage"] == "ingest" for event in default)
        assert all(event.get("audience") != "ops" for event in default)
        assert not any("812KB" in (event.get("message") or "") for event in default)

        ops = client.get(f"/api/jobs/{job_id}/history?audience=ops").json()["events"]
        assert ops
        assert all(event["audience"] == "ops" for event in ops)
        assert any("812KB" in (event.get("message") or "") for event in ops)
        assert not any(event["stage"] == "preview_ready" for event in ops)

        all_events = client.get(f"/api/jobs/{job_id}/history?audience=all").json()["events"]
        assert len(all_events) == len(default) + len(ops)

    def test_get_job_history_missing_is_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        assert client.get("/api/jobs/nope/history").status_code == 404

    def test_reingest_keeps_and_appends_history(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        first = _ingest(client)
        first_events = client.get(f"/api/jobs/{first['id']}/history").json()["events"]
        second = _ingest(client, overwrite=True)
        assert second["id"] == first["id"]
        second_events = client.get(f"/api/jobs/{second['id']}/history").json()["events"]
        assert second_events[: len(first_events)] == first_events
        assert second_events[-1]["stage"] == "preview_ready"
        assert len(second_events) > len(first_events)

    def test_sse_emits_preview_ready(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        job_id = _ingest(client)["id"]
        stages = []
        with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = json.loads(line[len("data:") :].strip())
                stages.append(payload["stage"])
                assert payload["occurred_at"]
                if payload["stage"] == "preview_ready":
                    break
        assert "ingest" in stages
        assert "preview_ready" in stages

    def test_publish_job_returns_new_upload_job(self, tmp_path: Path) -> None:
        publisher = MagicMock()
        album = MagicMock()
        album.productUrl = "https://photos.example/album-1"
        publisher.publish.return_value = album
        gp = MagicMock(name="GooglePhotos")
        gp_factory = MagicMock(return_value=gp)
        client = _client(tmp_path, publisher=publisher, gp_factory=gp_factory)

        job_id = _ingest(client)["id"]
        response = _publish(client, job_id)
        assert response.status_code == 201, response.text
        started = response.json()
        assert started["id"] != job_id
        assert started["type"] == "upload"
        assert started["source_job_id"] == job_id
        assert started["status"] in {"pending", "running", "done"}
        body = _wait_job(client, started["id"])
        assert body["status"] == "done"
        assert body["type"] == "upload"
        assert body["product_url"] == "https://photos.example/album-1"
        assert body["source_job_id"] == job_id
        preview = client.get(f"/api/jobs/{job_id}").json()
        assert preview["id"] == job_id
        assert preview["type"] == "preview"
        assert preview["status"] == "done"
        assert preview["product_url"] is None
        publisher.publish.assert_called_once()
        assert publisher.publish.call_args.args[0] is gp
        gp_factory.assert_called_once_with("ya29.test-token")

    def test_publish_returns_running_before_finish(self, tmp_path: Path) -> None:
        started = threading.Event()
        release = threading.Event()
        publisher = MagicMock()
        album = MagicMock()
        album.productUrl = "https://photos.example/album-1"

        def slow_publish(*_args: object, **_kwargs: object) -> MagicMock:
            started.set()
            assert release.wait(timeout=5)
            return album

        publisher.publish.side_effect = slow_publish
        client = _client(tmp_path, publisher=publisher)

        job_id = _ingest(client)["id"]
        response = _publish(client, job_id)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["id"] != job_id
        assert body["type"] == "upload"
        assert body["status"] in {"pending", "running"}
        assert body["product_url"] is None
        assert body["source_job_id"] == job_id
        assert started.wait(timeout=2)
        still = client.get(f"/api/jobs/{body['id']}").json()
        assert still["status"] == "running"
        assert still["product_url"] is None
        release.set()
        done = _wait_job(client, body["id"])
        assert done["status"] == "done"
        assert done["product_url"] == "https://photos.example/album-1"

    def test_publish_failure_returns_201_then_marks_upload_failed(self, tmp_path: Path) -> None:
        publisher = MagicMock()
        publisher.publish.side_effect = RuntimeError("oauth failed")
        client = _client(tmp_path, publisher=publisher)

        job_id = _ingest(client)["id"]
        response = _publish(client, job_id)
        assert response.status_code == 201, response.text
        upload_id = response.json()["id"]
        failed = _wait_job(client, upload_id, status="failed")
        assert failed["type"] == "upload"
        assert "oauth failed" in (failed["error"] or "")
        preview = client.get(f"/api/jobs/{job_id}").json()
        assert preview["type"] == "preview"
        assert preview["status"] == "done"

    def test_publish_missing_job_is_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        assert _publish(client, "nope").status_code == 404

    def test_publish_twice_creates_two_upload_jobs(self, tmp_path: Path) -> None:
        publisher = MagicMock()
        first_album = MagicMock()
        first_album.productUrl = "https://photos.example/album-1"
        second_album = MagicMock()
        second_album.productUrl = "https://photos.example/album-2"
        publisher.publish.side_effect = [first_album, second_album]
        client = _client(tmp_path, publisher=publisher)

        job_id = _ingest(client)["id"]
        first = _publish(client, job_id)
        assert first.status_code == 201
        assert first.json()["id"] != job_id
        first_done = _wait_job(client, first.json()["id"])
        assert first_done["product_url"] == "https://photos.example/album-1"
        second = _publish(client, job_id)
        assert second.status_code == 201, second.text
        assert second.json()["id"] != job_id
        assert second.json()["id"] != first.json()["id"]
        second_done = _wait_job(client, second.json()["id"])
        assert second_done["status"] == "done"
        assert second_done["type"] == "upload"
        assert second_done["product_url"] == "https://photos.example/album-2"
        assert publisher.publish.call_count == 2
        preview = client.get(f"/api/jobs/{job_id}").json()
        assert preview["type"] == "preview"
        assert preview["status"] == "done"
        listed = client.get("/api/jobs").json()["jobs"]
        assert {job["id"] for job in listed} == {
            job_id,
            first.json()["id"],
            second.json()["id"],
        }

    def test_sse_after_publish_reaches_done_on_upload_job(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        job_id = _ingest(client)["id"]
        published = _publish(client, job_id)
        assert published.status_code == 201
        upload_id = published.json()["id"]
        preview_stages = [
            event["stage"]
            for event in client.get(f"/api/jobs/{job_id}/history").json()["events"]
        ]
        assert "preview_ready" in preview_stages
        assert "done" not in preview_stages
        stages = []
        with client.stream(
            "GET", f"/api/jobs/{upload_id}/events?phase=publish"
        ) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = json.loads(line[len("data:") :].strip())
                stages.append(payload["stage"])
                if payload["stage"] in {"done", "error"}:
                    break
        assert "preview_ready" not in stages
        assert "publish" in stages
        assert "done" in stages
        assert stages[-1] == "done"

    def test_list_jobs_empty(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        response = client.get("/api/jobs")
        assert response.status_code == 200
        assert response.json() == {"jobs": []}

    def test_list_jobs_newest_first_summaries(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        first = _ingest(client)
        second = _ingest(client, _arles_multipart())
        response = client.get("/api/jobs")
        assert response.status_code == 200
        listed = response.json()["jobs"]
        assert {job["id"] for job in listed} == {first["id"], second["id"]}
        assert first["id"] != second["id"]
        assert listed[0]["created_at"] >= listed[1]["created_at"]
        assert listed[0]["id"] == second["id"]
        assert listed[0]["number"] == 2
        assert listed[1]["number"] == 1
        mini = next(job for job in listed if job["id"] == first["id"])
        arles = next(job for job in listed if job["id"] == second["id"])
        assert "preview" not in mini
        assert mini["title"] == "2/8/2012 - mini fixture"
        assert mini["item_count"] == 1
        assert mini["status"] == "done"
        assert mini["type"] == "preview"
        assert mini["product_url"] is None
        assert mini["error"] is None
        assert mini["created_at"]
        assert mini["updated_at"]
        assert mini["finished_at"]
        assert mini["duration_seconds"] is not None
        assert mini["duration_seconds"] >= 0
        assert mini["last_stage"] == "preview_ready"
        assert arles["title"] == "2/8/2012 - Day 1 – Delphi"
        assert arles["item_count"] == 2
        assert first["created_at"]
        detail = client.get(f"/api/jobs/{first['id']}").json()
        assert detail["preview"]["title"] == "2/8/2012 - mini fixture"
        assert detail["created_at"] == first["created_at"]
        assert detail["finished_at"]
        assert detail["number"] == 1
        assert first["number"] == 1
        assert second["number"] == 2

    def test_jobs_reload_from_disk_on_new_app(self, tmp_path: Path) -> None:
        client1 = _client(tmp_path)
        created = _ingest(client1)
        job_id = created["id"]
        client1.patch(f"/api/jobs/{job_id}", json={"title": "Kept title"})

        client2 = _client(tmp_path)
        listed = client2.get("/api/jobs").json()["jobs"]
        assert listed[0]["id"] == job_id
        assert listed[0]["title"] == "Kept title"
        got = client2.get(f"/api/jobs/{job_id}").json()
        assert got["preview"]["title"] == "Kept title"
        assert got["preview"]["items"][0]["id"] == "20120802_01"
        assert got["created_at"] == created["created_at"]

    def test_reprocess_reparses_without_new_upload(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        job_id = _ingest(client)["id"]
        client.patch(f"/api/jobs/{job_id}", json={"title": "Edited title"})
        edited = client.get(f"/api/jobs/{job_id}").json()
        assert edited["preview"]["title"] == "Edited title"
        assert edited["user_edited"] is True

        response = client.post(f"/api/jobs/{job_id}/reprocess")
        assert response.status_code == 200, response.text
        assert response.json()["id"] == job_id
        body = _wait_job(client, job_id)
        assert body["status"] == "done"
        assert body["type"] == "preview"
        assert body["preview"]["title"] == "2/8/2012 - mini fixture"
        assert body["user_edited"] is False

    def test_reprocess_new_mode_creates_prefixed_album_and_keeps_original(
        self,
        tmp_path: Path,
    ) -> None:
        client = _client(tmp_path)
        original = _ingest(client)
        job_id = original["id"]
        original_caption = original["preview"]["items"][0]["caption"]
        client.patch(
            f"/api/jobs/{job_id}",
            json={"title": "Edited title", "captions": {"20120802_01": "kept caption"}},
        )
        assert client.get(f"/api/jobs/{job_id}").json()["user_edited"] is True

        response = client.post(
            f"/api/jobs/{job_id}/reprocess",
            json={"mode": "new", "title_prefix": "Reprocessed · "},
        )
        assert response.status_code == 200, response.text
        new_id = response.json()["id"]
        assert new_id != job_id
        new_job = _wait_job(client, new_id)
        assert new_job["status"] == "done"
        assert new_job["type"] == "preview"
        assert new_job["preview"]["title"] == "Reprocessed · Edited title"
        assert new_job["user_edited"] is False
        assert new_job["folder_label"] == original.get("folder_label")
        assert new_job["import_origin"] == "folder"

        kept = client.get(f"/api/jobs/{job_id}").json()
        assert kept["id"] == job_id
        assert kept["preview"]["title"] == "Edited title"
        assert kept["preview"]["items"][0]["caption"] == "kept caption"
        assert kept["user_edited"] is True
        assert kept["preview"]["items"][0]["caption"] != original_caption

    def test_reprocess_missing_job_is_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        assert client.post("/api/jobs/nope/reprocess").status_code == 404

    def test_delete_job_returns_204_and_wipes_disk(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        job_id = _ingest(client)["id"]
        job_dir = tmp_path / "jobs" / job_id
        assert job_dir.is_dir()
        assert (job_dir / "index.html").is_file()

        response = client.delete(f"/api/jobs/{job_id}")
        assert response.status_code == 204
        assert response.content == b""
        assert client.get(f"/api/jobs/{job_id}").status_code == 404
        assert client.get("/api/jobs").json() == {"jobs": []}
        assert not job_dir.exists()

        client2 = _client(tmp_path)
        assert client2.get(f"/api/jobs/{job_id}").status_code == 404
        assert client2.get("/api/jobs").json() == {"jobs": []}

    def test_delete_missing_job_is_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        assert client.delete("/api/jobs/nope").status_code == 404

    def test_archive_job_hides_from_lists_keeps_get(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        job_id = _ingest(client)["id"]
        job_dir = tmp_path / "jobs" / job_id
        assert (job_dir / "index.html").is_file()

        response = client.post(f"/api/jobs/{job_id}/archive")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["archived_ids"] == [job_id]
        assert body["job"]["id"] == job_id
        assert body["job"]["archived_at"]
        assert body["job"]["status"] == "done"
        assert body["job"]["preview"]["title"] == "2/8/2012 - mini fixture"

        listed = client.get("/api/jobs").json()["jobs"]
        assert listed == []
        deduped = client.get("/api/jobs?dedupe=true").json()["jobs"]
        assert [row["id"] for row in deduped] == [job_id]
        assert deduped[0]["title"] == "2/8/2012 - mini fixture"
        assert deduped[0]["archived_at"]
        included = client.get("/api/jobs?include_archived=true").json()["jobs"]
        assert [row["id"] for row in included] == [job_id]
        assert included[0]["archived_at"]
        got = client.get(f"/api/jobs/{job_id}")
        assert got.status_code == 200
        assert got.json()["archived_at"]
        assert (job_dir / "index.html").is_file()

        reprocessed = client.post(f"/api/jobs/{job_id}/reprocess")
        assert reprocessed.status_code == 200, reprocessed.text
        done = _wait_job(client, job_id)
        assert done["status"] == "done"
        assert done["archived_at"]
        assert client.get("/api/jobs").json()["jobs"] == []
        still_album = client.get("/api/jobs?dedupe=true").json()["jobs"]
        assert [row["id"] for row in still_album] == [job_id]

        again = client.post("/api/jobs", files=_mini_multipart())
        assert again.status_code == 201, again.text
        assert again.json()["id"] != job_id

    def test_archive_forbidden_on_running_job(self, tmp_path: Path) -> None:
        api = _api(tmp_path)
        store = api.app.state.deps.store
        job = store.create(api.jobs_root)
        store.set_status(job.id, "running", job_type="preview")

        response = api.client.post(f"/api/jobs/{job.id}/archive")
        assert response.status_code == 409, response.text
        assert response.json()["detail"] == "job is still active"
        listed = api.client.get("/api/jobs").json()["jobs"]
        assert [row["id"] for row in listed] == [job.id]
        assert listed[0]["archived_at"] is None

    def test_archive_cascades_descendants(self, tmp_path: Path) -> None:
        from tests.support.builders import PreviewBuilder

        api = _api(tmp_path)
        store = api.app.state.deps.store
        hub = store.create(
            api.jobs_root,
            job_type="scrape",
            scrape_url="https://albums.example/hub",
        )
        child = store.create(
            api.jobs_root,
            job_type="scrape",
            parent_job_id=hub.id,
            scrape_url="https://albums.example/day1",
        )
        preview = store.create(api.jobs_root, parent_job_id=child.id)
        store.set_preview(preview.id, PreviewBuilder().with_title("Day 1").build())
        store.set_status(hub.id, "done", job_type="scrape")
        store.set_status(child.id, "done", job_type="scrape")

        response = api.client.post(f"/api/jobs/{hub.id}/archive")
        assert response.status_code == 200, response.text
        archived_ids = set(response.json()["archived_ids"])
        assert archived_ids == {hub.id, child.id, preview.id}
        listed = {row["id"] for row in api.client.get("/api/jobs").json()["jobs"]}
        assert listed == set()
        deduped = api.client.get("/api/jobs?dedupe=true").json()["jobs"]
        assert [row["id"] for row in deduped] == [preview.id]
        assert deduped[0]["title"] == "Day 1"
        assert api.client.get(f"/api/jobs/{preview.id}").status_code == 200

    def test_archive_missing_job_is_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        assert client.post("/api/jobs/nope/archive").status_code == 404

    def test_reprocess_then_publish_again(self, tmp_path: Path) -> None:
        publisher = MagicMock()
        first_album = MagicMock()
        first_album.productUrl = "https://photos.example/album-1"
        second_album = MagicMock()
        second_album.productUrl = "https://photos.example/album-2"
        publisher.publish.side_effect = [first_album, second_album]
        client = _client(tmp_path, publisher=publisher)

        job_id = _ingest(client)["id"]
        published = _publish(client, job_id)
        assert published.status_code == 201
        upload_id = published.json()["id"]
        first_done = _wait_job(client, upload_id)
        assert first_done["product_url"] == "https://photos.example/album-1"

        reprocessed = client.post(f"/api/jobs/{job_id}/reprocess")
        assert reprocessed.status_code == 200
        assert reprocessed.json()["id"] == job_id
        done = _wait_job(client, job_id)
        assert done["status"] == "done"
        assert done["type"] == "preview"

        still_upload = client.get(f"/api/jobs/{upload_id}").json()
        assert still_upload["type"] == "upload"
        assert still_upload["product_url"] == "https://photos.example/album-1"

        again = _publish(client, job_id)
        assert again.status_code == 201, again.text
        assert again.json()["id"] != job_id
        assert again.json()["id"] != upload_id
        again_done = _wait_job(client, again.json()["id"])
        assert again_done["status"] == "done"
        assert again_done["type"] == "upload"
        assert again_done["product_url"] == "https://photos.example/album-2"
        assert publisher.publish.call_count == 2

    def test_reingest_same_album_without_overwrite_is_409(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        first = _ingest(client)
        second = client.post("/api/jobs", files=_mini_multipart())
        assert second.status_code == 409, second.text
        detail = second.json()["detail"]
        assert detail["code"] == "album_exists"
        assert detail["existing_id"] == first["id"]
        assert detail["title"] == "2/8/2012 - mini fixture"

        listed = client.get("/api/jobs").json()["jobs"]
        assert [job["id"] for job in listed] == [first["id"]]
        got = client.get(f"/api/jobs/{first['id']}").json()
        assert got["id"] == first["id"]
        assert got["created_at"] == first["created_at"]
        assert got["preview"]["title"] == "2/8/2012 - mini fixture"
        assert got["status"] == "done"
        assert got["type"] == "preview"
        job_dirs = [path.name for path in (tmp_path / "jobs").iterdir() if path.is_dir()]
        assert job_dirs == [first["id"]]

    def test_reingest_same_album_reuses_job_and_single_library_row(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        first = _ingest(client)
        second = _ingest(client, overwrite=True)
        assert second["id"] == first["id"]
        assert second["created_at"] == first["created_at"]
        assert second["status"] == "done"
        assert second["type"] == "preview"
        listed = client.get("/api/jobs").json()["jobs"]
        assert [job["id"] for job in listed] == [first["id"]]
        assert listed[0]["title"] == "2/8/2012 - mini fixture"

    def test_reingest_same_album_keeps_upload_history(self, tmp_path: Path) -> None:
        publisher = MagicMock()
        album = MagicMock()
        album.productUrl = "https://photos.example/album-1"
        publisher.publish.return_value = album
        client = _client(tmp_path, publisher=publisher)

        first = _ingest(client)
        published = _publish(client, first["id"])
        assert published.status_code == 201
        upload_id = published.json()["id"]
        _wait_job(client, upload_id)

        second = _ingest(client, overwrite=True)
        assert second["id"] == first["id"]
        assert second["created_at"] == first["created_at"]
        assert second["status"] == "done"
        assert second["type"] == "preview"
        upload = client.get(f"/api/jobs/{upload_id}").json()
        assert upload["type"] == "upload"
        assert upload["product_url"] == "https://photos.example/album-1"
        listed = client.get("/api/jobs").json()["jobs"]
        assert {job["id"] for job in listed} == {first["id"], upload_id}
        albums = client.get("/api/jobs?dedupe=true").json()["jobs"]
        assert [job["id"] for job in albums] == [first["id"]]
        assert albums[0]["product_url"] == "https://photos.example/album-1"

    def test_reprocess_keeps_single_library_row(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        job_id = _ingest(client)["id"]
        reprocessed = client.post(f"/api/jobs/{job_id}/reprocess")
        assert reprocessed.status_code == 200
        assert reprocessed.json()["id"] == job_id
        _wait_job(client, job_id)
        listed = client.get("/api/jobs").json()["jobs"]
        assert [job["id"] for job in listed] == [job_id]

    def test_list_dedupes_duplicate_titles_already_on_disk(self, tmp_path: Path) -> None:
        from datetime import datetime, timezone

        from src.export.preview import AlbumPreview, PreviewItem
        from src.jobs.store import JobStore

        jobs_root = tmp_path / "jobs"
        store = JobStore()
        older = store.create(jobs_root)
        newer = store.create(jobs_root)
        preview = AlbumPreview(
            title="Same album",
            description=None,
            multi_index=False,
            items=(
                PreviewItem(
                    id="20120802_01",
                    relpath="hrimages/20120802_01hr.JPG",
                    caption="",
                    size_bytes=1,
                ),
            ),
        )
        older.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        newer.created_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        store.set_preview(older.id, preview)
        store.set_preview(newer.id, preview)
        store.mark_done(older.id, "https://photos.example/kept")

        client = _client(tmp_path)
        listed = client.get("/api/jobs").json()["jobs"]
        assert {job["id"] for job in listed} == {older.id, newer.id}
        albums = client.get("/api/jobs?dedupe=true").json()["jobs"]
        assert [job["id"] for job in albums] == [newer.id]
        assert albums[0]["product_url"] == "https://photos.example/kept"
        assert albums[0]["title"] == "Same album"

    def test_publish_blank_token_is_401(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        job_id = _ingest(client)["id"]
        response = _publish(client, job_id, token="  ")
        assert response.status_code == 401
        assert "google access token required" in response.json()["detail"]

    def test_auth_config_returns_client_id_and_scopes(
        self,
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
        client = _client(tmp_path)
        response = client.get("/api/auth/config")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["client_id"] == "cid.apps.googleusercontent.com"
        assert "client_secret" not in body
        assert set(body) == {"client_id", "scopes"}
        assert body["scopes"] == [
            "https://www.googleapis.com/auth/photoslibrary",
            "https://www.googleapis.com/auth/photoslibrary.appendonly",
            "https://www.googleapis.com/auth/photoslibrary.sharing",
            "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata",
        ]

    def test_auth_config_json_env_without_file(
        self,
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
        monkeypatch.setenv("GOOGLE_CLIENT_SECRETS", str(tmp_path / "no-secrets.json"))
        monkeypatch.setenv(
            "GOOGLE_OAUTH_CLIENT_SECRETS",
            json.dumps(
                {
                    "web": {
                        "client_id": "json-env.apps.googleusercontent.com",
                        "client_secret": "must-not-leak",
                    }
                }
            ),
        )
        client = _client(tmp_path)
        response = client.get("/api/auth/config")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["client_id"] == "json-env.apps.googleusercontent.com"
        assert "client_secret" not in body
        assert "must-not-leak" not in response.text
        assert set(body) == {"client_id", "scopes"}

    def test_auth_config_empty_env_falls_back_to_file(
        self,
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secrets = tmp_path / "client_secrets.json"
        secrets.write_text(
            json.dumps(
                {
                    "web": {
                        "client_id": "file.apps.googleusercontent.com",
                        "client_secret": "must-not-leak",
                    }
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "   ")
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS", "")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRETS_JSON", "")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRETS", str(secrets))
        client = _client(tmp_path)
        response = client.get("/api/auth/config")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["client_id"] == "file.apps.googleusercontent.com"
        assert "client_secret" not in body
        assert "must-not-leak" not in response.text

    def test_post_job_auto_publish_starts_upload_child(self, tmp_path: Path) -> None:
        publisher = MagicMock()
        album = MagicMock()
        album.productUrl = "https://photos.example/auto"
        publisher.publish.return_value = album
        gp_factory = MagicMock(return_value=MagicMock())
        client = _client(tmp_path, publisher=publisher, gp_factory=gp_factory)

        body = _ingest(client, auto_publish=True, token="ya29.auto-token")
        assert body["type"] == "preview"
        assert body["status"] == "done"
        assert body["auto_publish"] is True
        deadline = time.monotonic() + 5
        children = []
        while time.monotonic() < deadline:
            children = client.get(f"/api/jobs/{body['id']}/children").json()["jobs"]
            if any(row["type"] == "upload" for row in children):
                break
            time.sleep(0.05)
        assert any(row["type"] == "upload" for row in children), children
        assert len(children) == 1
        upload = children[0]
        assert upload["type"] == "upload"
        assert upload["parent_job_id"] == body["id"]
        done = _wait_job(client, upload["id"])
        assert done["product_url"] == "https://photos.example/auto"
        gp_factory.assert_called_with("ya29.auto-token")
        publisher.publish.assert_called()
        db_path = tmp_path / "jobs" / "migrator.sqlite"
        assert db_path.is_file()
        assert b"ya29.auto-token" not in db_path.read_bytes()
        listed = client.get("/api/jobs").json()["jobs"]
        preview_row = next(row for row in listed if row["id"] == body["id"])
        assert preview_row["auto_publish"] is True

    def test_post_job_without_auto_publish_has_no_upload_child(self, tmp_path: Path) -> None:
        publisher = MagicMock()
        client = _client(tmp_path, publisher=publisher)
        body = _ingest(client)
        assert body.get("auto_publish") is False
        children = client.get(f"/api/jobs/{body['id']}/children").json()["jobs"]
        assert children == []
        publisher.publish.assert_not_called()

    def test_post_job_auto_publish_without_token_is_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        response = client.post("/api/jobs?auto_publish=true", files=_mini_multipart())
        assert response.status_code == 400
        assert "token" in response.text.lower()

    def test_auto_publish_token_not_written_to_job_json(self, tmp_path: Path) -> None:
        from src.api.app import create_app

        publisher = MagicMock()
        album = MagicMock()
        album.productUrl = "https://photos.example/json"
        publisher.publish.return_value = album
        app = create_app(
            jobs_root=tmp_path / "jobs",
            state_backend="json",
            publisher=publisher,
            gp_factory=MagicMock(return_value=MagicMock()),
        )
        client = TestClient(app)
        response = client.post(
            "/api/jobs?auto_publish=true",
            files=_mini_multipart(),
            data={"access_token": "ya29.secret-json-token"},
        )
        assert response.status_code == 201, response.text
        job_id = response.json()["id"]
        for path in (tmp_path / "jobs").rglob("*.json"):
            text = path.read_text(encoding="utf-8")
            assert "ya29.secret-json-token" not in text
        meta = json.loads((tmp_path / "jobs" / job_id / "job.json").read_text(encoding="utf-8"))
        assert meta["auto_publish"] is True

    def test_auth_config_missing_is_503(
        self,
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRETS", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRETS_JSON", raising=False)
        monkeypatch.setenv("GOOGLE_CLIENT_SECRETS", str(tmp_path / "no-secrets.json"))
        client = _client(tmp_path)
        response = client.get("/api/auth/config")
        assert response.status_code == 503

