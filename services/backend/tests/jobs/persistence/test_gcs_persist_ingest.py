"""TDD: ingest/scrape persist album files via ArtifactStore (GCS-safe)."""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

from src.jobs.ingest import IngestService
from src.jobs.persistence.gcs_artifacts import GcsArtifactStore
from src.jobs.store import JobStore
from tests.support.builders import PreviewBuilder
from tests.support.fakes.gcs import FakeGcsClient


class TestIngestPersistsViaArtifactStore:
    def test_ingest_finish_calls_store_materialize_album(
        self, tmp_path: Path
    ) -> None:
        """Workspace-only writes leave GCS cold after scale-to-zero; use store."""
        store = MagicMock()
        job = MagicMock()
        job.id = "job-1"
        job.root = tmp_path / "jobs" / "job-1"
        job.root.mkdir(parents=True)
        job.status = "pending"
        job.type = "preview"
        job.owner_id = "owner-a"
        job.source_job_id = None
        store.get.return_value = job
        store.find_by_title.return_value = None
        store.materialize_album.return_value = job.root

        parser = MagicMock()
        parser.parse.return_value = (
            PreviewBuilder().with_title("Mini album").no_journal().build()
        )
        events = MagicMock()
        workspace = MagicMock()

        files = [
            ("index.html", b"<html></html>", None),
            ("hrimages/a.jpg", b"jpeg", None),
        ]
        service = IngestService(
            store=store,
            parser=parser,
            events=events,
            workspace=workspace,
        )
        service.finish("job-1", files)

        store.materialize_album.assert_called_once_with("job-1", files)
        workspace.assert_not_called()

    def test_job_store_materialize_album_uploads_under_owner_prefix(
        self, tmp_path: Path
    ) -> None:
        gcs = FakeGcsClient()
        artifacts = GcsArtifactStore(
            tmp_path / "cache",
            bucket="test-bucket",
            prefix="jobs",
            client=gcs,
        )
        store = JobStore.load(tmp_path / "jobs", artifacts=artifacts)
        job = store.create(tmp_path / "jobs", owner_id="owner-a")
        files = [
            ("index.html", b"<html><span class='gallerytitle'>Mini</span></html>", None),
            ("hrimages/a.jpg", b"\xff\xd8\xff", None),
        ]
        root = store.materialize_album(job.id, files)
        assert (root / "index.html").is_file()
        assert gcs.bucket("test-bucket").blob(
            f"jobs/users/owner-a/{job.id}/index.html"
        ).exists()
        assert gcs.bucket("test-bucket").blob(
            f"jobs/users/owner-a/{job.id}/hrimages/a.jpg"
        ).exists()
        shutil.rmtree(tmp_path / "cache" / job.id)
        hydrated = artifacts.local_root(job.id, owner_id="owner-a")
        assert (hydrated / "index.html").is_file()


class TestJobStoreLoadSkipsGcsHydrate:
    def test_load_does_not_download_album_bytes(self, tmp_path: Path) -> None:
        """Cloud Run boot must not pull every album before uvicorn binds."""
        gcs = FakeGcsClient()
        cache = tmp_path / "cache"
        artifacts = GcsArtifactStore(
            cache, bucket="test-bucket", prefix="jobs", client=gcs
        )
        store = JobStore.load(tmp_path / "jobs", artifacts=artifacts)
        job = store.create(tmp_path / "jobs", owner_id="owner-a")
        store.materialize_album(
            job.id,
            [
                ("index.html", b"<html></html>", None),
                ("hrimages/a.jpg", b"JPEG", None),
            ],
        )
        store.set_preview(
            job.id,
            PreviewBuilder().with_title("Cold cache").no_journal().build(),
        )
        shutil.rmtree(cache / job.id, ignore_errors=True)
        gcs.download_to_filename_calls = 0

        reloaded = JobStore.load(
            tmp_path / "jobs",
            artifacts=GcsArtifactStore(
                cache, bucket="test-bucket", prefix="jobs", client=gcs
            ),
        )
        assert gcs.download_to_filename_calls == 0
        assert not (cache / job.id / "index.html").is_file()

        root = reloaded.ensure_local_root(job.id)
        assert gcs.download_to_filename_calls >= 1
        assert (root / "index.html").is_file()


class TestGcsOwnerScopedPaths:
    def test_object_keys_include_users_owner_segment(self, tmp_path: Path) -> None:
        gcs = FakeGcsClient()
        store = GcsArtifactStore(
            tmp_path,
            bucket="b",
            prefix="jobs",
            client=gcs,
        )
        store.materialize(
            "job-1",
            [("index.html", b"<html></html>", None)],
            owner_id="user-1",
        )
        assert gcs.bucket("b").blob("jobs/users/user-1/job-1/index.html").exists()
        assert not gcs.bucket("b").blob("jobs/job-1/index.html").exists()

    def test_missing_owner_keeps_legacy_job_prefix(self, tmp_path: Path) -> None:
        gcs = FakeGcsClient()
        store = GcsArtifactStore(
            tmp_path,
            bucket="b",
            prefix="jobs",
            client=gcs,
        )
        store.materialize(
            "job-1",
            [("index.html", b"<html></html>", None)],
        )
        assert gcs.bucket("b").blob("jobs/job-1/index.html").exists()
