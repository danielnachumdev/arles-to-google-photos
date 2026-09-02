"""TDD: local sqlite mirrored to GCS when APP_ENV is cloud (no DATABASE_URL)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from src.jobs.persistence import (
    build_state_store,
    resolve_database_url,
    sqlite_gcs_object_key,
)
from src.jobs.persistence.gcs_sqlite import GcsSqliteMirror
from src.jobs.persistence.sqlalchemy_state import (
    DB_NAME,
    SqlAlchemyStateStore,
    create_engine_for_url,
    reject_gcs_database_url,
)
from src.jobs.store import JobNotFoundError
from tests.support.builders import JobRecordBuilder
from tests.support.fakes.gcs import FakeGcsClient


@pytest.fixture(autouse=True)
def _cloud_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "cloud")


def _pragma_journal_mode(store: SqlAlchemyStateStore) -> str:
    with store._engine.connect() as conn:
        value = conn.execute(text("PRAGMA journal_mode")).scalar()
    return str(value or "").upper()


def _flush_mirror(store: Any) -> None:
    mirror = getattr(store, "sqlite_mirror", None)
    assert mirror is not None
    mirror.flush()


class TestSqliteGcsObjectKey:
    def test_default_prefix_and_empty(self) -> None:
        assert sqlite_gcs_object_key("jobs") == "jobs/migrator.sqlite"
        assert sqlite_gcs_object_key("jobs/v1") == "jobs/v1/migrator.sqlite"
        assert sqlite_gcs_object_key("") == "migrator.sqlite"
        assert sqlite_gcs_object_key(" /jobs/ ") == "jobs/migrator.sqlite"


class TestRejectGcsDatabaseUrl:
    def test_gs_and_gcs_schemes_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="GCS URI|gs://|gcs://"):
            reject_gcs_database_url("gs://my-bucket/migrator.sqlite")
        with pytest.raises(ValueError, match="GCS URI|gs://|gcs://"):
            reject_gcs_database_url("gcs://other-bucket/state.sqlite")
        reject_gcs_database_url("sqlite:///C:/tmp/migrator.sqlite")
        reject_gcs_database_url("postgresql+psycopg://u:p@localhost/arles")

    def test_resolve_and_engine_reject_gs_database_url(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DATABASE_URL", "gs://my-bucket/migrator.sqlite")
        with pytest.raises(ValueError, match="GCS URI|gs://"):
            resolve_database_url(tmp_path)
        with pytest.raises(ValueError, match="GCS URI|gs://"):
            build_state_store(tmp_path)
        monkeypatch.delenv("DATABASE_URL")
        with pytest.raises(ValueError, match="GCS URI|gcs://"):
            resolve_database_url(tmp_path, url="gcs://bucket/db")
        with pytest.raises(ValueError, match="GCS URI|gs://"):
            create_engine_for_url("gs://bucket/migrator.sqlite")


class TestGcsSqliteMirror:
    def test_hydrate_on_open(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)
        monkeypatch.delenv("GCS_PREFIX", raising=False)
        fake = FakeGcsClient()
        source = build_state_store(
            tmp_path / "source",
            gcs_client=fake,
            gcs_bucket="test-bucket",
        )
        source.create(JobRecordBuilder().with_id("kept").build())
        source.close()
        assert fake.bucket("test-bucket").blob("jobs/migrator.sqlite").exists()

        dest = tmp_path / "dest"
        dest.mkdir()
        assert not (dest / DB_NAME).exists()
        store = build_state_store(
            dest,
            gcs_client=fake,
            gcs_bucket="test-bucket",
        )
        assert store.get("kept").id == "kept"
        assert (dest / DB_NAME).is_file()
        store.close()

    def test_upload_after_create(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)
        monkeypatch.delenv("GCS_PREFIX", raising=False)
        fake = FakeGcsClient()
        first = tmp_path / "first"
        store = build_state_store(
            first,
            gcs_client=fake,
            gcs_bucket="test-bucket",
        )
        store.create(JobRecordBuilder().with_id("new-1").build())
        _flush_mirror(store)
        blob = fake.bucket("test-bucket").blob("jobs/migrator.sqlite")
        assert blob.exists()
        store.close()

        second = tmp_path / "second"
        second.mkdir()
        restored = build_state_store(
            second,
            gcs_client=fake,
            gcs_bucket="test-bucket",
        )
        assert restored.get("new-1").id == "new-1"
        restored.close()

    def test_postgres_url_skips_sqlite_gcs_sync(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.jobs.persistence import sqlalchemy_state as sa_mod

        remote = tmp_path / "standin.sqlite"
        standin_url = "sqlite:///" + remote.resolve().as_posix()
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/arles")
        fake = FakeGcsClient()
        real_create = sa_mod.create_engine_for_url

        def fake_create(url: str, **_kwargs: object) -> object:
            return real_create(standin_url)

        monkeypatch.setattr(sa_mod, "create_engine_for_url", fake_create)
        store = build_state_store(
            tmp_path / "jobs",
            gcs_client=fake,
            gcs_bucket="test-bucket",
        )
        assert isinstance(store, SqlAlchemyStateStore)
        assert store.sqlite_mirror is None
        store.create(JobRecordBuilder().with_id("pg-1").build())
        assert not fake.bucket("test-bucket").blob("jobs/migrator.sqlite").exists()
        store.close()

    def test_gcs_mirror_uses_delete_journal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)
        fake = FakeGcsClient()
        mirrored = build_state_store(
            tmp_path / "gcs",
            gcs_client=fake,
            gcs_bucket="test-bucket",
        )
        assert _pragma_journal_mode(mirrored) == "DELETE"
        mirrored.close()

        monkeypatch.setenv("APP_ENV", "local")
        local = build_state_store(tmp_path / "local")
        assert _pragma_journal_mode(local) == "WAL"
        local.close()

    def test_upload_after_save_delete_event_meta(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.jobs.events import JobEvent

        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)
        fake = FakeGcsClient()
        store = build_state_store(
            tmp_path,
            gcs_client=fake,
            gcs_bucket="gs://uri-bucket/custom/pre",
        )
        assert isinstance(store, SqlAlchemyStateStore)
        assert store.sqlite_mirror is not None
        assert store.sqlite_mirror.object_key == "custom/pre/migrator.sqlite"
        record = store.create(JobRecordBuilder().with_id("job-1").build())
        record.status = "done"
        store.save(record)
        store.append_event(
            "job-1",
            JobEvent(job_id="job-1", stage="ingest", message="ok"),
        )
        store.set_meta("max_concurrent_jobs", "4")
        _flush_mirror(store)
        blob = fake.bucket("uri-bucket").blob("custom/pre/migrator.sqlite")
        assert blob.exists()
        store.delete("job-1")
        store.close()

        other = tmp_path / "other"
        other.mkdir()
        restored = build_state_store(
            other,
            gcs_client=fake,
            gcs_bucket="gs://uri-bucket/custom/pre",
        )
        with pytest.raises(JobNotFoundError):
            restored.get("job-1")
        assert restored.get_meta("max_concurrent_jobs") == "4"
        restored.close()

    def test_empty_prefix_key_is_bucket_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("GCS_PREFIX", raising=False)
        fake = FakeGcsClient()
        store = build_state_store(
            tmp_path,
            gcs_client=fake,
            gcs_bucket="test-bucket",
            gcs_prefix="",
        )
        store.create(JobRecordBuilder().with_id("root-1").build())
        _flush_mirror(store)
        assert fake.bucket("test-bucket").blob("migrator.sqlite").exists()
        assert not fake.bucket("test-bucket").blob("jobs/migrator.sqlite").exists()
        store.close()

    def test_create_app_mirrors_sqlite_when_cloud(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("APP_ENV", "local")
        from src.api.app import create_app

        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)
        monkeypatch.setenv("APP_ENV", "cloud")
        monkeypatch.setenv("GCS_BUCKET", "app-bucket")
        fake = FakeGcsClient()
        app = create_app(jobs_root=tmp_path / "app", artifact_client=fake)
        state = app.state.deps.store._state
        assert isinstance(state, SqlAlchemyStateStore)
        assert state.sqlite_mirror is not None
        state.create(JobRecordBuilder().with_id("app-1").build())
        _flush_mirror(state)
        assert fake.bucket("app-bucket").blob("jobs/migrator.sqlite").exists()

    def test_local_app_env_ignores_bucket_no_mirror(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("APP_ENV", "local")
        monkeypatch.setenv("GCS_BUCKET", "app-bucket")
        fake = FakeGcsClient()
        store = build_state_store(tmp_path, gcs_client=fake, gcs_bucket="app-bucket")
        assert isinstance(store, SqlAlchemyStateStore)
        assert store.sqlite_mirror is None
        assert _pragma_journal_mode(store) == "WAL"
        store.create(JobRecordBuilder().with_id("local-1").build())
        assert not fake.bucket("app-bucket").blob("jobs/migrator.sqlite").exists()
        store.close()

    def test_unset_app_env_defaults_to_cloud_mirror(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        fake = FakeGcsClient()
        store = build_state_store(
            tmp_path,
            gcs_client=fake,
            gcs_bucket="app-bucket",
        )
        assert isinstance(store, SqlAlchemyStateStore)
        assert store.sqlite_mirror is not None
        store.create(JobRecordBuilder().with_id("cloud-1").build())
        _flush_mirror(store)
        assert fake.bucket("app-bucket").blob("jobs/migrator.sqlite").exists()
        store.close()

    def test_mirror_constructor_requires_bucket(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="GCS_BUCKET"):
            GcsSqliteMirror(tmp_path / DB_NAME, bucket="", client=FakeGcsClient())

    def test_mirror_properties_and_upload_noop(self, tmp_path: Path) -> None:
        fake = FakeGcsClient()
        local = tmp_path / "missing" / DB_NAME
        mirror = GcsSqliteMirror(
            local,
            bucket="prop-bucket",
            prefix="jobs/v1",
            client=fake,
        )
        assert mirror.bucket_name == "prop-bucket"
        assert mirror.prefix == "jobs/v1"
        assert mirror.local_path == local
        assert mirror.object_key == "jobs/v1/migrator.sqlite"
        assert mirror.interval_s == 1.0
        mirror.upload()
        assert not fake.bucket("prop-bucket").blob(mirror.object_key).exists()
        mirror.close()

    def test_schedule_uploads_at_most_once_per_interval(self, tmp_path: Path) -> None:
        fake = FakeGcsClient()
        local = tmp_path / DB_NAME
        local.write_bytes(b"sqlite-bytes")
        mirror = GcsSqliteMirror(
            local,
            bucket="rate-bucket",
            prefix="jobs",
            client=fake,
            interval_s=0.25,
        )
        for _ in range(8):
            mirror.schedule()
        time.sleep(0.05)
        assert fake.upload_from_filename_calls <= 1
        deadline = time.time() + 1.0
        while fake.upload_from_filename_calls < 1 and time.time() < deadline:
            time.sleep(0.02)
        assert fake.upload_from_filename_calls == 1
        assert fake.bucket("rate-bucket").blob("jobs/migrator.sqlite").exists()
        time.sleep(0.28)
        mirror.schedule()
        deadline = time.time() + 1.0
        while fake.upload_from_filename_calls < 2 and time.time() < deadline:
            time.sleep(0.02)
        assert fake.upload_from_filename_calls == 2
        mirror.close()

    def test_create_does_not_block_on_gcs_upload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        fake = FakeGcsClient()
        store = build_state_store(
            tmp_path,
            gcs_client=fake,
            gcs_bucket="test-bucket",
        )
        mirror = store.sqlite_mirror
        assert mirror is not None
        original_upload = mirror.upload

        def slow_upload() -> None:
            time.sleep(1.2)
            original_upload()

        mirror.upload = slow_upload  # type: ignore[method-assign]
        started = time.perf_counter()
        store.create(JobRecordBuilder().with_id("fast-1").build())
        elapsed = time.perf_counter() - started
        assert elapsed < 0.4
        store.close()

    def test_unsupported_journal_mode_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="journal_mode"):
            create_engine_for_url("sqlite:///:memory:", journal_mode="MEMORY")
