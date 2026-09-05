"""API edge paths: media variants, publish errors, deps, history, ingest stamps."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.export.preview import AlbumPreview
from src.jobs.store import JobStore
from tests.support.album import AlbumTree
from tests.support.api import MigratorApi
from tests.support.suites import ApiClientSuite, ScrapeFakeSuite
from tests.support.suites import TmpPathSuite


class TestMediaVariantEdges(ApiClientSuite):
    def test_image_play_uses_original_thumb_is_low_res(self) -> None:
        api = self.make_api()
        job = api.ingest()
        job_id = job["id"]
        original = api.client.get(f"/api/jobs/{job_id}/media/20120802_01")
        play = api.client.get(f"/api/jobs/{job_id}/media/20120802_01?variant=play")
        thumb = api.client.get(f"/api/jobs/{job_id}/media/20120802_01?variant=thumb")
        assert original.status_code == 200
        assert play.status_code == 200
        assert thumb.status_code == 200
        assert play.content == original.content
        assert thumb.content.startswith(b"\xff\xd8")
        assert len(thumb.content) < len(original.content)

    def test_missing_item_and_missing_file_are_404(self) -> None:
        api = self.make_api()
        job = api.ingest()
        missing_item = api.client.get(f"/api/jobs/{job['id']}/media/nope")
        assert missing_item.status_code == 404
        rel = job["preview"]["items"][0]["relpath"]
        (api.jobs_root / job["id"] / rel).unlink()
        missing_file = api.client.get(f"/api/jobs/{job['id']}/media/20120802_01")
        assert missing_file.status_code == 404

    def test_browser_playable_video_play_falls_back_to_relpath(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "src.jobs.ingest.ensure_local_video_previews", lambda root: None
        )
        index = """<!DOCTYPE html>
<html><body>
  <span class="gallerytitle">Mp4 clip</span>
  <a href="imagepages/clip01.html"><img src="thumbnails/TN_clip01.jpg"></a>
</body></html>
"""
        files = [
            ("files", ("index.html", index.encode("utf-8"), "text/html")),
            ("files", ("imagepages/clip01.html", b"<html></html>", "text/html")),
            ("files", ("hrimages/clip01hr.mp4", b"ftyp-src", "video/mp4")),
        ]
        api = self.make_api()
        job = api.ingest(files)
        item = job["preview"]["items"][0]
        assert item["kind"] == "video"
        play = api.client.get(f"/api/jobs/{job['id']}/media/clip01?variant=play")
        assert play.status_code == 200
        assert play.content == b"ftyp-src"


class TestPublishAndRestartEdges(ApiClientSuite):
    def test_publish_preview_not_ready_is_409(self, tmp_path: Path) -> None:
        api = self.make_api()
        store: JobStore = api.app.state.deps.store
        job = store.create(api.jobs_root)
        response = api.publish(job.id)
        assert response.status_code == 409
        assert "preview not ready" in response.json()["detail"]

    def test_publish_already_in_progress_is_409(self, tmp_path: Path) -> None:
        api = self.make_api()
        preview = api.ingest()
        store: JobStore = api.app.state.deps.store
        upload = store.create_upload_from(preview["id"])
        store.set_status(upload.id, "running", job_type="upload")
        response = api.publish(upload.id)
        assert response.status_code == 409
        assert "in progress" in response.json()["detail"]

    def test_publish_no_items_is_400(self, tmp_path: Path) -> None:
        api = self.make_api()
        store: JobStore = api.app.state.deps.store
        job = store.create(api.jobs_root)
        store.set_preview(
            job.id,
            AlbumPreview(title="Empty", description=None, multi_index=False, items=()),
        )
        response = api.publish(job.id)
        assert response.status_code == 400
        assert "no items" in response.json()["detail"]

    def test_restart_not_cancelled_is_409(self, tmp_path: Path) -> None:
        api = self.make_api()
        job = api.ingest()
        response = api.client.post(f"/api/jobs/{job['id']}/restart", json={})
        assert response.status_code == 409

    def test_restart_preview_not_cancelled_is_409(self, tmp_path: Path) -> None:
        api = self.make_api()
        job = api.ingest()
        response = api.client.get(f"/api/jobs/{job['id']}/restart-preview")
        assert response.status_code == 409

    def test_patch_unknown_caption_is_400(self, tmp_path: Path) -> None:
        api = self.make_api()
        job = api.ingest()
        response = api.client.patch(
            f"/api/jobs/{job['id']}",
            json={"captions": {"missing": "nope"}},
        )
        assert response.status_code == 400

    def test_reprocess_upload_job_is_409(self, tmp_path: Path) -> None:
        api = self.make_api()
        preview = api.ingest()
        published = api.publish(preview["id"])
        assert published.status_code == 201
        upload_id = published.json()["id"]
        api.wait_job(upload_id)
        response = api.client.post(f"/api/jobs/{upload_id}/reprocess")
        assert response.status_code == 409


class TestHistoryAndIngestEdges(ApiClientSuite):
    def test_history_invalid_audience_defaults_to_ui(self, tmp_path: Path) -> None:
        api = self.make_api()
        job = api.ingest()
        response = api.client.get(f"/api/jobs/{job['id']}/history?audience=nope")
        assert response.status_code == 200
        events = response.json()["events"]
        assert events
        assert all(event["audience"] == "ui" for event in events)

    def test_last_modified_form_field_is_accepted(self, tmp_path: Path) -> None:
        api = self.make_api(tmp_path)
        stamp_ms = int(datetime(2012, 8, 2, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
        files = list(AlbumTree.mini_multipart())
        files.extend(("lastModified", (None, str(stamp_ms))) for _ in range(len(files)))
        response = api.client.post("/api/jobs", files=files)
        assert response.status_code == 201, response.text
        job = api.wait_job(response.json()["id"])
        assert job["status"] == "done"

    def test_album_upload_allows_more_than_starlette_default_file_cap(
        self, tmp_path: Path
    ) -> None:
        """Starlette defaults to 1000 files; album hubs need a higher cap."""
        from src.api.routers import jobs as jobs_router

        api = self.make_api(tmp_path)
        index = (
            b"<!DOCTYPE html><html><body>"
            b'<span class="gallerytitle">Big hub</span>'
            b"</body></html>"
        )
        files: list = [("files", ("index.html", index, "text/html"))]
        # Just over Starlette's default max_files=1000 (index + 1001 pads).
        for i in range(1001):
            files.append(
                (
                    "files",
                    (f"hrimages/pad_{i:04d}hr.JPG", b"\xff\xd8\xff\xd9", "image/jpeg"),
                )
            )
        file_count = sum(1 for name, _ in files if name == "files")
        files.extend(
            ("lastModified", (None, str(1_700_000_000_000 + i)))
            for i in range(file_count)
        )
        assert file_count == 1002
        assert jobs_router.MULTIPART_MAX_FILES >= file_count
        assert jobs_router.MULTIPART_MAX_FIELDS >= file_count
        response = api.client.post("/api/jobs", files=files)
        assert "Too many files" not in response.text
        assert "Maximum number of files is 1000" not in response.text
        # Missing imagepages → parse may fail after accept; multipart must parse.
        assert response.status_code in {201, 400}, response.text

    def test_hub_folder_upload_fans_out_leaf_children(self, tmp_path: Path) -> None:
        api = self.make_api(tmp_path)
        jpeg = b"\xff\xd8\xff\xd9"
        files = [
            (
                "files",
                (
                    "index.html",
                    b'<!DOCTYPE html><html><head>'
                    b'<meta http-equiv="refresh" content="0;url=./Aug10/index.html">'
                    b"</head><body></body></html>",
                    "text/html",
                ),
            ),
        ]
        for day, item_id, title in (
            ("Aug10", "20120810_01", "Aug 10"),
            ("Aug11", "20120811_01", "Aug 11"),
        ):
            files.append(
                (
                    "files",
                    (
                        f"{day}/index.html",
                        (
                            f'<!DOCTYPE html><html><body>'
                            f'<span class="gallerytitle">{title}</span>'
                            f'<a href="imagepages/{item_id}.html">'
                            f'<img src="thumbnails/TN_{item_id}.JPG"></a>'
                            f"</body></html>"
                        ).encode("utf-8"),
                        "text/html",
                    ),
                )
            )
            files.append(
                (
                    "files",
                    (
                        f"{day}/imagepages/{item_id}.html",
                        b'<html><body><div class="imagetitle">shot</div></body></html>',
                        "text/html",
                    ),
                )
            )
            files.append(
                (
                    "files",
                    (f"{day}/hrimages/{item_id}hr.JPG", jpeg, "image/jpeg"),
                )
            )
        response = api.client.post("/api/jobs", files=files)
        assert response.status_code == 201, response.text
        parent_id = response.json()["id"]
        parent = api.wait_job(parent_id, status="done")
        assert "only redirects" not in (parent.get("error") or "")
        children = api.client.get(f"/api/jobs/{parent_id}/children").json()["jobs"]
        assert len(children) == 2
        for child in children:
            detail = api.wait_job(child["id"], status="done")
            assert detail["status"] == "done"
            assert detail["preview"] is not None
            assert len(detail["preview"]["items"]) == 1
            assert detail["parent_job_id"] == parent_id
            assert detail["source_job_id"] == parent_id


    def test_default_gp_factory_is_invoked_on_publish(self, tmp_path: Path) -> None:
        from src.api.app import create_app
        from tests.support.fakes.publisher import fake_publisher
        from tests.support.waits import JobWaiter

        app = create_app(
            jobs_root=tmp_path / "jobs",
            publisher=fake_publisher(product_url="https://photos.example/default-gp"),
        )
        client = TestClient(app)
        created = client.post("/api/jobs", files=AlbumTree.mini_multipart())
        assert created.status_code == 201, created.text
        preview_id = created.json()["id"]
        JobWaiter().http_status(client, preview_id)
        published = client.post(
            f"/api/jobs/{preview_id}/publish",
            json={"access_token": "ya29.default-factory"},
        )
        assert published.status_code == 201, published.text
        upload = JobWaiter().http_status(client, published.json()["id"])
        assert upload["product_url"] == "https://photos.example/default-gp"


class TestScrapeApiEdges(ScrapeFakeSuite):
    def test_blank_url_is_400(self, tmp_path: Path) -> None:
        api = self.make_api()
        response = api.client.post("/api/jobs/scrape", json={"url": "  "})
        assert response.status_code == 400

    def test_web_reprocess_retries_leaf_scrape(self, tmp_path: Path) -> None:
        api = self.make_api()
        created = api.scrape("https://albums.example/day1", wait=True)
        preview_id = created["preview_job_id"] or created["child_ids"][0]
        api.wait_job(preview_id)
        response = api.client.post(f"/api/jobs/{preview_id}/reprocess")
        assert response.status_code == 200, response.text
        api.wait_job(preview_id)

class TestRequirePreviewDeps(TmpPathSuite):
    def test_require_preview_and_get_deps_errors(self) -> None:
        from src.api.deps import get_deps, require_preview

        request = MagicMock()
        request.app.state.deps = None
        with pytest.raises(RuntimeError, match="not configured"):
            get_deps(request)

        job = MagicMock()
        job.preview = None
        with pytest.raises(HTTPException) as exc:
            require_preview(job)
        assert exc.value.status_code == 409

