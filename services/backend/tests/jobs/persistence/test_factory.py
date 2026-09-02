"""Persistence factory + path guards + sqlite column migration."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.api.app import create_app
from src.jobs.persistence import (
    build_artifact_store,
    build_state_store,
    local_sqlite_url,
    resolve_app_env,
    resolve_artifact_bucket,
    resolve_database_url,
)
from src.jobs.persistence.fs_artifacts import FsArtifactStore
from src.jobs.persistence.gcs_artifacts import GcsArtifactStore
from src.jobs.persistence.gcs_sqlite import GcsSqliteMirror, sqlite_gcs_object_key
from src.jobs.persistence.json_state import JsonStateStore
from src.jobs.persistence.paths import (
    normalize_gcs_prefix,
    parse_gcs_uri,
    validate_job_id,
    validate_relpath,
)
from src.jobs.persistence.sqlalchemy_state import (
    SqlAlchemyStateStore,
    reject_gcs_database_url,
)
from src.jobs.persistence.sqlite_state import SqliteStateStore
from tests.support.fakes.gcs import FakeGcsClient
from src.jobs.store import parse_created_at, parse_user_edited, parse_warnings
from tests.support.builders import JobRecordBuilder, PreviewBuilder
from tests.support.persistence import JsonStateStoreBackend, SqliteStateStoreBackend
from tests.support.suites import StateStoreSuite
from tests.support.suites import TmpPathSuite










class TestJsonStateStoreContract(StateStoreSuite):
    backend = JsonStateStoreBackend()

    def test_duplicate_create_raises(self, state, tmp_path: Path) -> None:
        del tmp_path
        state.create(JobRecordBuilder().with_id("dup").build())
        with pytest.raises(ValueError, match="already exists"):
            state.create(JobRecordBuilder().with_id("dup").build())

    def test_corrupt_meta_is_skipped_in_list(self, tmp_path: Path) -> None:
        job_dir = tmp_path / "broken"
        job_dir.mkdir()
        (job_dir / "job.json").write_text("{not json", encoding="utf-8")
        store = self.backend.create(tmp_path)
        assert store.list_all() == []

    def test_events_file_as_list_loads(self, tmp_path: Path) -> None:
        from src.jobs.store import EVENTS_NAME, JOB_META_NAME

        job_dir = tmp_path / "listed-events"
        job_dir.mkdir()
        (job_dir / JOB_META_NAME).write_text(
            json.dumps(
                {
                    "id": "listed-events",
                    "status": "done",
                    "type": "preview",
                    "created_at": "2024-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        (job_dir / EVENTS_NAME).write_text(
            json.dumps(
                [
                    {
                        "job_id": "listed-events",
                        "stage": "ingest",
                        "message": "ok",
                        "occurred_at": "2024-01-01T00:00:01",
                    }
                ]
            ),
            encoding="utf-8",
        )
        store = self.backend.create(tmp_path)
        events = store.list_events("listed-events")
        assert events[0].stage == "ingest"
        assert events[0].occurred_at.tzinfo is not None


class TestSqliteStateStoreContract(StateStoreSuite):
    backend = SqliteStateStoreBackend()

    def test_duplicate_create_raises(self, state, tmp_path: Path) -> None:
        del tmp_path
        state.create(JobRecordBuilder().with_id("dup").build())
        with pytest.raises(ValueError, match="already exists"):
            state.create(JobRecordBuilder().with_id("dup").build())

    def test_corrupt_preview_json_skipped_in_list(self, tmp_path: Path) -> None:
        store = self.backend.create(tmp_path)
        store.create(JobRecordBuilder().with_id("good").build())
        db = tmp_path / "migrator.sqlite"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO jobs (id, type, status, created_at, preview_json) VALUES (?, ?, ?, ?, ?)",
            ("bad", "preview", "pending", "2024-01-01T00:00:00+00:00", "{not json"),
        )
        conn.commit()
        conn.close()
        ids = {record.id for record in store.list_all()}
        assert "good" in ids
        assert "bad" not in ids

    def test_corrupt_extra_and_headers_json_are_ignored(self, tmp_path: Path) -> None:
        store = self.backend.create(tmp_path)
        store.create(
            JobRecordBuilder()
            .with_id("soft")
            .with_preview(PreviewBuilder().with_title("Soft").build())
            .build()
        )
        db = tmp_path / "migrator.sqlite"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "UPDATE jobs SET extra_json = ?, scrape_headers_json = ?, warnings_json = ? WHERE id = ?",
            ("{bad", "{bad", "{bad", "soft"),
        )
        conn.commit()
        conn.close()
        record = store.get("soft")
        assert record.extra is None
        assert record.scrape_headers is None
        assert record.warnings == []

class TestPersistenceFactory(TmpPathSuite):
    def test_resolve_app_env_default_and_aliases(self, monkeypatch) -> None:
        monkeypatch.delenv("APP_ENV", raising=False)
        assert resolve_app_env() == "cloud"
        monkeypatch.setenv("APP_ENV", "")
        assert resolve_app_env() == "cloud"
        monkeypatch.setenv("APP_ENV", "   ")
        assert resolve_app_env() == "cloud"
        for alias in ("cloud", "prod", "production", "CLOUD", "Prod"):
            assert resolve_app_env(alias) == "cloud"
            monkeypatch.setenv("APP_ENV", alias)
            assert resolve_app_env() == "cloud"
        for alias in ("local", "dev", "development", "LOCAL", "Dev"):
            assert resolve_app_env(alias) == "local"
            monkeypatch.setenv("APP_ENV", alias)
            assert resolve_app_env() == "local"
        with pytest.raises(ValueError, match="APP_ENV"):
            resolve_app_env("staging")
        monkeypatch.setenv("APP_ENV", "staging")
        with pytest.raises(ValueError, match="APP_ENV"):
            resolve_app_env()

    def test_resolve_database_url_blank_vs_env(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)
        local = resolve_database_url(tmp_path)
        assert local == local_sqlite_url(tmp_path)
        assert local.startswith("sqlite:///")
        assert local.endswith("migrator.sqlite") or local.rstrip("/").endswith(
            "migrator.sqlite"
        )

        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/arles")
        monkeypatch.setenv(
            "SQLALCHEMY_DATABASE_URL", "postgresql+psycopg://alias/ignored"
        )
        assert (
            resolve_database_url(tmp_path)
            == "postgresql+psycopg://u:p@localhost/arles"
        )

        monkeypatch.delenv("DATABASE_URL")
        assert resolve_database_url(tmp_path) == "postgresql+psycopg://alias/ignored"

        assert (
            resolve_database_url(
                tmp_path, url="postgresql+psycopg://explicit/db"
            )
            == "postgresql+psycopg://explicit/db"
        )
        assert resolve_database_url(tmp_path, url="") == local_sqlite_url(tmp_path)
        assert resolve_database_url(tmp_path, url="   ") == local_sqlite_url(tmp_path)

    def test_resolve_artifact_bucket_blank_vs_env(self, monkeypatch) -> None:
        monkeypatch.delenv("GCS_BUCKET", raising=False)
        monkeypatch.delenv("ARTIFACT_BUCKET", raising=False)
        assert resolve_artifact_bucket() == ""
        assert resolve_artifact_bucket("") == ""

        monkeypatch.setenv("GCS_BUCKET", "primary-bucket")
        monkeypatch.setenv("ARTIFACT_BUCKET", "alias-bucket")
        assert resolve_artifact_bucket() == "primary-bucket"
        assert resolve_artifact_bucket("explicit") == "explicit"

        monkeypatch.delenv("GCS_BUCKET")
        assert resolve_artifact_bucket() == "alias-bucket"
        assert resolve_artifact_bucket("  ") == ""

    def test_build_state_store_local_sqlite_by_default(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)
        store = build_state_store(tmp_path)
        assert isinstance(store, SqlAlchemyStateStore)
        assert isinstance(store, SqliteStateStore)
        assert store.url == local_sqlite_url(tmp_path)
        store.create(JobRecordBuilder().with_id("local-1").build())
        assert (tmp_path / "migrator.sqlite").is_file()
        store.close()

        json_store = build_state_store(tmp_path / "json", use_json=True)
        assert isinstance(json_store, JsonStateStore)

    def test_build_state_store_uses_explicit_sqlite_url_as_fake_remote(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        remote = tmp_path / "remote.sqlite"
        url = "sqlite:///" + remote.resolve().as_posix()
        jobs = tmp_path / "jobs"
        store = build_state_store(jobs, url=url)
        assert isinstance(store, SqlAlchemyStateStore)
        assert store.url == url
        store.create(JobRecordBuilder().with_id("remote-1").build())
        assert remote.is_file()
        assert not (jobs / "migrator.sqlite").exists()
        store.close()

    def test_build_state_store_database_url_env_uses_fake_remote_engine(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from src.jobs.persistence import sqlalchemy_state as sa_mod

        remote = tmp_path / "standin.sqlite"
        standin_url = "sqlite:///" + remote.resolve().as_posix()
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/arles")
        seen: list[str] = []
        real_create = sa_mod.create_engine_for_url

        def fake_create(url: str, **_kwargs: object) -> object:
            seen.append(url)
            return real_create(standin_url)

        monkeypatch.setattr(sa_mod, "create_engine_for_url", fake_create)
        store = build_state_store(tmp_path / "jobs")
        assert seen == ["postgresql+psycopg://u:p@localhost/arles"]
        assert isinstance(store, SqlAlchemyStateStore)
        assert store.url == "postgresql+psycopg://u:p@localhost/arles"
        store.create(JobRecordBuilder().with_id("pg-fake").build())
        assert remote.is_file()
        store.close()

    def test_build_artifact_store_local_ignores_bucket(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("APP_ENV", "local")
        monkeypatch.setenv("GCS_BUCKET", "from-env")
        monkeypatch.setenv("ARTIFACT_BUCKET", "alias-bucket")
        assert isinstance(build_artifact_store(tmp_path), FsArtifactStore)
        assert isinstance(
            build_artifact_store(tmp_path / "explicit", bucket="env-bucket"),
            FsArtifactStore,
        )

    def test_build_artifact_store_cloud_uses_gcs(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("APP_ENV", "cloud")
        monkeypatch.delenv("GCS_BUCKET", raising=False)
        monkeypatch.delenv("ARTIFACT_BUCKET", raising=False)
        monkeypatch.delenv("GCS_PREFIX", raising=False)
        with pytest.raises(ValueError, match="GCS_BUCKET"):
            build_artifact_store(tmp_path)
        with pytest.raises(ValueError, match="GCS_BUCKET"):
            build_artifact_store(tmp_path / "blank", bucket="")

        fake = FakeGcsClient()
        gcs = build_artifact_store(
            tmp_path / "gcs",
            bucket="env-bucket",
            prefix="explicit",
            client=fake,
        )
        assert isinstance(gcs, GcsArtifactStore)
        assert gcs.bucket_name == "env-bucket"
        assert gcs.prefix == "explicit"
        defaulted = build_artifact_store(
            tmp_path / "gcs-default",
            bucket="env-bucket",
            client=fake,
        )
        assert defaulted.prefix == "jobs"

        monkeypatch.setenv("GCS_BUCKET", "from-env")
        monkeypatch.setenv("GCS_PREFIX", "albums")
        from_env = build_artifact_store(tmp_path / "env", client=fake)
        assert isinstance(from_env, GcsArtifactStore)
        assert from_env.bucket_name == "from-env"
        assert from_env.prefix == "albums"

        monkeypatch.delenv("GCS_BUCKET")
        monkeypatch.setenv("ARTIFACT_BUCKET", "gs://alias-bucket/custom/pre")
        aliased = build_artifact_store(tmp_path / "alias", client=fake)
        assert isinstance(aliased, GcsArtifactStore)
        assert aliased.bucket_name == "alias-bucket"
        assert aliased.prefix == "custom/pre"

        uri = build_artifact_store(
            tmp_path / "uri",
            bucket="gcs://uri-bucket/custom/pre",
            client=fake,
        )
        assert isinstance(uri, GcsArtifactStore)
        assert uri.bucket_name == "uri-bucket"
        assert uri.prefix == "custom/pre"

    def test_build_artifact_store_unset_app_env_defaults_to_cloud(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("GCS_BUCKET", raising=False)
        monkeypatch.delenv("ARTIFACT_BUCKET", raising=False)
        with pytest.raises(ValueError, match="GCS_BUCKET"):
            build_artifact_store(tmp_path)
        fake = FakeGcsClient()
        monkeypatch.setenv("GCS_BUCKET", "default-cloud")
        store = build_artifact_store(tmp_path / "env", client=fake)
        assert isinstance(store, GcsArtifactStore)
        assert store.bucket_name == "default-cloud"

    def test_build_state_store_cloud_sqlite_requires_bucket(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("APP_ENV", "cloud")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)
        monkeypatch.delenv("GCS_BUCKET", raising=False)
        monkeypatch.delenv("ARTIFACT_BUCKET", raising=False)
        with pytest.raises(ValueError, match="GCS_BUCKET"):
            build_state_store(tmp_path)

    def test_create_app_selects_sqlite_fs_or_gcs(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("APP_ENV", "local")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)
        monkeypatch.setenv("GCS_BUCKET", "ignored-locally")
        app = create_app(jobs_root=tmp_path / "local")
        store = app.state.deps.store
        assert isinstance(store._state, SqlAlchemyStateStore)
        assert store._state.url == local_sqlite_url(tmp_path / "local")
        assert isinstance(store._artifacts, FsArtifactStore)
        assert store._state.sqlite_mirror is None

        fake = FakeGcsClient()
        monkeypatch.setenv("APP_ENV", "cloud")
        monkeypatch.setenv("GCS_BUCKET", "app-bucket")
        gcs_app = create_app(
            jobs_root=tmp_path / "gcs-app",
            artifact_client=fake,
        )
        artifacts = gcs_app.state.deps.store._artifacts
        assert isinstance(artifacts, GcsArtifactStore)
        assert artifacts.bucket_name == "app-bucket"

        monkeypatch.setenv("APP_ENV", "local")
        json_app = create_app(
            jobs_root=tmp_path / "json-app",
            state_backend="json",
        )
        assert isinstance(json_app.state.deps.store._state, JsonStateStore)

    def test_create_engine_for_url_postgres_and_injected_engine(
        self, tmp_path: Path
    ) -> None:
        from src.jobs.persistence.sqlalchemy_state import create_engine_for_url

        pg = create_engine_for_url("postgresql+psycopg://u:p@localhost/arles")
        assert pg.dialect.name == "postgresql"
        pg.dispose()

        memory = create_engine_for_url("sqlite:///:memory:")
        assert memory.dialect.name == "sqlite"
        injected_dir = tmp_path / "injected"
        store = SqlAlchemyStateStore(injected_dir, engine=memory, url="sqlite:///:memory:")
        assert store.url == "sqlite:///:memory:"
        store.create(JobRecordBuilder().with_id("mem-1").build())
        assert store.get("mem-1").id == "mem-1"
        store.close()

    def test_persistence_module_getattr(self) -> None:
        import src.jobs.persistence as pers

        assert pers.JsonStateStore is JsonStateStore
        assert pers.SqliteStateStore is SqliteStateStore
        assert pers.SqlAlchemyStateStore is SqlAlchemyStateStore
        assert pers.SqliteStateStore is pers.SqlAlchemyStateStore
        assert pers.FsArtifactStore is FsArtifactStore
        assert pers.GcsArtifactStore is GcsArtifactStore
        assert pers.GcsSqliteMirror is GcsSqliteMirror
        assert pers.sqlite_gcs_object_key is sqlite_gcs_object_key
        assert pers.reject_gcs_database_url is reject_gcs_database_url
        with pytest.raises(AttributeError):
            pers.NoSuchBackend  # type: ignore[attr-defined]

    def test_validate_job_id_rejects_absolute_and_traversal(self) -> None:
        assert validate_job_id("job-1") == "job-1"
        with pytest.raises(ValueError):
            validate_job_id("")
        with pytest.raises(ValueError):
            validate_job_id("..")
        with pytest.raises(ValueError):
            validate_job_id("a/b")
        with pytest.raises(ValueError):
            validate_job_id(str(Path.cwd() / "outside-job"))

    def test_validate_relpath_and_parse_gcs_uri(self) -> None:
        assert validate_relpath(r"hrimages\a.jpg") == "hrimages/a.jpg"
        with pytest.raises(ValueError, match="traversal"):
            validate_relpath("../secret")
        with pytest.raises(ValueError, match="traversal"):
            validate_relpath("/abs")
        assert parse_gcs_uri("gcs://my-bucket") == ("my-bucket", "")
        assert parse_gcs_uri("gs://my-bucket/jobs/v1") == ("my-bucket", "jobs/v1")
        with pytest.raises(ValueError):
            parse_gcs_uri("s3://nope")
        with pytest.raises(ValueError, match="missing bucket"):
            parse_gcs_uri("gcs://")
        with pytest.raises(ValueError, match="missing bucket"):
            parse_gcs_uri("gs:// /prefix")
        with pytest.raises(ValueError, match="invalid GCS prefix"):
            normalize_gcs_prefix("jobs/../secret")

    def test_incomplete_legacy_sqlite_gains_columns_via_alembic_bridge(
        self, tmp_path: Path
    ) -> None:
        """Legacy volumes missing later columns are altered then stamped."""
        db = tmp_path / "migrator.sqlite"
        conn = sqlite3.connect(str(db))
        conn.executescript(
            """
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                product_url TEXT,
                created_at TEXT NOT NULL,
                folder_label TEXT,
                preview_json TEXT
            );
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                current INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0,
                extra_json TEXT,
                occurred_at TEXT NOT NULL
            );
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        conn.execute(
            "INSERT INTO jobs (id, type, status, created_at) VALUES (?, ?, ?, ?)",
            ("old-1", "preview", "pending", "2024-01-01T00:00:00+00:00"),
        )
        conn.commit()
        conn.close()

        store = SqliteStateStore(tmp_path)
        record = store.get("old-1")
        assert record.id == "old-1"
        store.save(
            JobRecordBuilder()
            .with_id("old-1")
            .with_status("done")
            .with_preview(PreviewBuilder().with_title("Migrated").build())
            .with_extra({"restarted_from": "x"})
            .with_warnings(["note"])
            .with_user_edited(True)
            .with_import_origin("folder")
            .build()
        )
        updated = store.get("old-1")
        assert updated.status == "done"
        assert updated.user_edited is True
        assert updated.extra == {"restarted_from": "x"}
        assert updated.warnings == ["note"]
        store.close()

    def test_parse_helpers_cover_legacy_shapes(self) -> None:
        assert parse_warnings("nope") == []
        assert parse_warnings(["  a  ", "", 2]) == ["a", "2"]
        assert parse_user_edited(True) is True
        assert parse_user_edited(1) is True
        assert parse_user_edited("YES") is True
        assert parse_user_edited("nope") is False
        assert parse_user_edited(None) is False
        naive = parse_created_at("2024-01-01T12:00:00")
        assert naive.tzinfo is timezone.utc
        nowish = parse_created_at(None)
        assert nowish.tzinfo is timezone.utc

