"""TDD: ArtifactStore GCS backend (fake client; no real bucket)."""
from __future__ import annotations

import os
import shutil
import sys
import types
import uuid
from pathlib import Path

import pytest

from src.jobs.persistence.artifacts import ArtifactStore
from src.jobs.persistence.gcs_artifacts import GcsArtifactStore
from tests.support.fakes.gcs import FakeGcsClient
from tests.support.suites import ArtifactStoreSuite


class TestGcsArtifactStore(ArtifactStoreSuite):
    gcs: FakeGcsClient

    def make_store(self, tmp_path: Path) -> ArtifactStore:
        self.gcs = FakeGcsClient()
        return GcsArtifactStore(
            tmp_path,
            bucket="test-bucket",
            prefix="jobs",
            client=self.gcs,
        )

    def test_gcs_artifact_store_is_artifact_store(self) -> None:
        assert issubclass(GcsArtifactStore, ArtifactStore)

    def test_constructor_requires_bucket(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="GCS_BUCKET"):
            GcsArtifactStore(tmp_path, bucket="", client=FakeGcsClient())

    def test_gs_uri_bucket_is_normalized(self, tmp_path: Path) -> None:
        store = GcsArtifactStore(
            tmp_path,
            bucket="gs://my-bucket",
            prefix="/jobs/v1/",
            client=FakeGcsClient(),
        )
        assert store.bucket_name == "my-bucket"
        assert store.prefix == "jobs/v1"

    def test_exists_and_list_use_gcs_when_cache_cold(self) -> None:
        self.artifacts.put("job-1", "hrimages/a.jpg", self.JPEG_BYTES)
        cache = self.tmp_path / "job-1"
        shutil.rmtree(cache)
        assert not cache.exists()

        assert self.artifacts.exists("job-1", "hrimages/a.jpg")
        assert set(self.artifacts.list("job-1")) == {"hrimages/a.jpg"}

    def test_local_root_hydrates_from_gcs(self) -> None:
        self.artifacts.materialize(
            "job-1",
            [
                ("index.html", self.HTML_BYTES, None),
                ("hrimages/a.jpg", self.JPEG_BYTES, None),
            ],
        )
        cache = self.tmp_path / "job-1"
        shutil.rmtree(cache)
        assert not cache.exists()

        root = self.artifacts.local_root("job-1")
        assert (root / "index.html").read_bytes() == self.HTML_BYTES
        # Media is a placeholder until ensure_file
        assert (root / "hrimages" / "a.jpg").is_file()
        assert (root / "hrimages" / "a.jpg").stat().st_size == 0
        assert (
            self.artifacts.ensure_file("job-1", "hrimages/a.jpg").read_bytes()
            == self.JPEG_BYTES
        )

    def test_materialize_discards_media_from_local_cache(self) -> None:
        self.artifacts.materialize(
            "job-1",
            [
                ("index.html", self.HTML_BYTES, None),
                ("hrimages/a.jpg", self.JPEG_BYTES, None),
            ],
        )
        cache = self.tmp_path / "job-1"
        assert (cache / "index.html").read_bytes() == self.HTML_BYTES
        # Placeholder remains (empty) so the parser can see membership.
        assert (cache / "hrimages" / "a.jpg").is_file()
        assert (cache / "hrimages" / "a.jpg").stat().st_size == 0
        assert self.artifacts.exists("job-1", "hrimages/a.jpg")

    def test_ensure_file_downloads_one_object(self) -> None:
        self.artifacts.put("job-1", "hrimages/a.jpg", self.JPEG_BYTES)
        before = self.gcs.download_to_filename_calls
        path = self.artifacts.ensure_file("job-1", "hrimages/a.jpg")
        assert path.read_bytes() == self.JPEG_BYTES
        assert self.gcs.download_to_filename_calls == before + 1
        # Second call uses warm cache (non-empty file)
        before = self.gcs.download_to_filename_calls
        again = self.artifacts.ensure_file("job-1", "hrimages/a.jpg")
        assert again.read_bytes() == self.JPEG_BYTES
        assert self.gcs.download_to_filename_calls == before

    def test_stage_file_keeps_full_local_bytes_without_gcs_upload(self) -> None:
        source = self.tmp_path / "src.jpg"
        source.write_bytes(self.JPEG_BYTES)
        before = list(self.gcs.bucket("test-bucket").list_blobs(prefix="jobs/job-1/"))
        self.artifacts.stage_file("job-1", "hrimages/a.jpg", source)
        dest = self.tmp_path / "job-1" / "hrimages" / "a.jpg"
        assert dest.is_file()
        assert dest.read_bytes() == self.JPEG_BYTES
        after = list(self.gcs.bucket("test-bucket").list_blobs(prefix="jobs/job-1/"))
        assert len(after) == len(before)
        # Later durable put uploads and placeholders.
        self.artifacts.put_file("job-1", "hrimages/a.jpg", dest)
        assert self.artifacts.exists("job-1", "hrimages/a.jpg")
        assert dest.stat().st_size == 0

    def test_local_root_hydrate_false_skips_download(self) -> None:
        self.artifacts.materialize(
            "job-1",
            [
                ("index.html", self.HTML_BYTES, None),
                ("hrimages/a.jpg", self.JPEG_BYTES, None),
            ],
        )
        cache = self.tmp_path / "job-1"
        shutil.rmtree(cache)
        assert not cache.exists()

        root = self.artifacts.local_root("job-1", hydrate=False)
        assert root == cache
        assert not cache.exists()
        assert not (cache / "index.html").exists()

    def test_local_root_does_not_overwrite_warm_cache(self) -> None:
        self.artifacts.put("job-1", "index.html", self.HTML_BYTES)
        local = self.tmp_path / "job-1" / "index.html"
        local.write_bytes(b"<html>edited locally</html>")

        root = self.artifacts.local_root("job-1")
        assert (root / "index.html").read_bytes() == b"<html>edited locally</html>"

    def test_delete_job_removes_gcs_objects_and_cache(self) -> None:
        self.artifacts.put("job-1", "index.html", self.HTML_BYTES)
        self.artifacts.delete_job("job-1")

        assert self.artifacts.list("job-1") == []
        assert not self.artifacts.exists("job-1", "index.html")
        assert not (self.tmp_path / "job-1").exists()
        blobs = list(self.gcs.bucket("test-bucket").list_blobs(prefix="jobs/job-1/"))
        assert blobs == []

    def test_list_omits_state_json_even_if_uploaded(self) -> None:
        self.artifacts.put("job-1", "index.html", self.HTML_BYTES)
        self.gcs.bucket("test-bucket").blob("jobs/job-1/job.json").upload_from_string(
            b"{}"
        )
        self.gcs.bucket("test-bucket").blob("jobs/job-1/events.json").upload_from_string(
            b"[]"
        )

        assert set(self.artifacts.list("job-1")) == {"index.html"}

    def test_empty_prefix_keys_are_job_id_relpath(self, tmp_path: Path) -> None:
        client = FakeGcsClient()
        store = GcsArtifactStore(
            tmp_path,
            bucket="test-bucket",
            prefix="",
            client=client,
        )
        store.put("job-1", "index.html", self.HTML_BYTES)
        assert client.bucket("test-bucket").blob("job-1/index.html").exists()
        assert not client.bucket("test-bucket").blob("jobs/job-1/index.html").exists()

    def test_put_does_not_upload_state_json(self) -> None:
        self.artifacts.put("job-1", "job.json", b"{}")
        assert not self.gcs.bucket("test-bucket").blob("jobs/job-1/job.json").exists()
        assert (self.tmp_path / "job-1" / "job.json").read_bytes() == b"{}"

    def test_retains_full_local_tree_is_false(self) -> None:
        assert self.artifacts.retains_full_local_tree is False

    def test_ensure_job_creates_cache_dir(self) -> None:
        self.artifacts.ensure_job("job-1")
        assert (self.tmp_path / "job-1").is_dir()

    def test_list_skips_directory_placeholder_blobs(self) -> None:
        self.artifacts.put("job-1", "index.html", self.HTML_BYTES)
        bucket = self.gcs.bucket("test-bucket")
        bucket.blob("jobs/job-1/").upload_from_string(b"")
        bucket.blob("jobs/job-1/hrimages/").upload_from_string(b"")
        assert set(self.artifacts.list("job-1")) == {"index.html"}

    def test_lazy_client_uses_google_cloud_storage(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeGcsClient()
        storage_mod = types.ModuleType("google.cloud.storage")

        class DummyClient:
            def bucket(self, name: str) -> object:
                return fake.bucket(name)

        storage_mod.Client = DummyClient  # type: ignore[attr-defined]
        cloud_mod = types.ModuleType("google.cloud")
        cloud_mod.storage = storage_mod  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "google.cloud", cloud_mod)
        monkeypatch.setitem(sys.modules, "google.cloud.storage", storage_mod)

        store = GcsArtifactStore(tmp_path, bucket="lazy-bucket")
        store.put("job-1", "index.html", self.HTML_BYTES)
        assert fake.bucket("lazy-bucket").blob("jobs/job-1/index.html").exists()


_LIVE = os.environ.get("ARLES_LIVE_GCS", "").strip().lower() in {"1", "true", "yes"}
_BUCKET = os.environ.get("GCS_BUCKET", "").strip()


@pytest.mark.gcs
@pytest.mark.skipif(not _LIVE, reason="live GCS tests disabled (set ARLES_LIVE_GCS=1)")
@pytest.mark.skipif(not _BUCKET, reason="GCS_BUCKET is required for live GCS tests")
class TestGcsArtifactStoreLive:
    def test_roundtrip_put_list_hydrate_delete(self, tmp_path: Path) -> None:
        env_prefix = os.environ.get("GCS_PREFIX", "jobs").strip().strip("/") or "jobs"
        store = GcsArtifactStore(
            tmp_path,
            bucket=_BUCKET,
            prefix=f"{env_prefix}/arles-live-tests",
        )
        job_id = f"live-{uuid.uuid4().hex[:12]}"
        payload = b"<html>live</html>"
        try:
            store.put(job_id, "index.html", payload)
            assert store.exists(job_id, "index.html")
            assert "index.html" in store.list(job_id)
            cache = tmp_path / job_id
            if cache.is_dir():
                shutil.rmtree(cache)
            root = store.local_root(job_id)
            assert (root / "index.html").read_bytes() == payload
        finally:
            store.delete_job(job_id)
