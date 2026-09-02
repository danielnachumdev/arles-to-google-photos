"""TDD: Alembic migrations create / upgrade the StateStore schema."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from src.jobs.persistence.migrate import (
    alembic_config,
    alembic_root,
    resolve_migrate_url,
    upgrade_head,
    upgrade_jobs_root,
)
from src.jobs.persistence.models import EVENTS_TABLE, JOBS_TABLE, META_TABLE
from src.jobs.persistence.sqlalchemy_state import (
    SqlAlchemyStateStore,
    create_engine_for_url,
    local_sqlite_url,
)
from src.jobs.persistence.sqlite_state import SqliteStateStore
from tests.support.builders import JobRecordBuilder


EXPECTED_JOB_COLUMNS = frozenset(c.name for c in JOBS_TABLE.columns)
EXPECTED_EVENT_COLUMNS = frozenset(c.name for c in EVENTS_TABLE.columns)
EXPECTED_META_COLUMNS = frozenset(c.name for c in META_TABLE.columns)
REQUIRED_TABLES = frozenset({"jobs", "events", "meta", "alembic_version"})


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


class TestAlembicLayout:
    def test_alembic_ini_and_versions_exist(self) -> None:
        root = alembic_root()
        assert (root / "alembic.ini").is_file()
        assert (root / "alembic" / "env.py").is_file()
        versions = root / "alembic" / "versions"
        assert versions.is_dir()
        assert any(versions.glob("*.py")), "expected at least one Alembic revision"

    def test_dockerfile_copies_alembic_assets(self) -> None:
        """Runtime image must ship alembic.ini + scripts (WORKDIR=/app)."""
        dockerfile = alembic_root() / "Dockerfile"
        text = dockerfile.read_text(encoding="utf-8")
        assert "alembic.ini" in text
        assert re.search(r"COPY\s+alembic\b", text) or "COPY alembic " in text


class TestUpgradeEmptyDatabase:
    def test_upgrade_head_creates_expected_tables_and_columns(
        self, tmp_path: Path
    ) -> None:
        url = local_sqlite_url(tmp_path)
        upgrade_head(url)

        db = tmp_path / "migrator.sqlite"
        assert db.is_file()
        conn = sqlite3.connect(str(db))
        try:
            names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert REQUIRED_TABLES.issubset(names)
            assert EXPECTED_JOB_COLUMNS <= _table_columns(conn, "jobs")
            assert EXPECTED_EVENT_COLUMNS <= _table_columns(conn, "events")
            assert EXPECTED_META_COLUMNS <= _table_columns(conn, "meta")
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            assert version is not None
            assert str(version[0]).strip()
        finally:
            conn.close()

    def test_upgrade_jobs_root_resolves_local_sqlite(self, tmp_path: Path) -> None:
        resolved = upgrade_jobs_root(tmp_path)
        assert resolved == local_sqlite_url(tmp_path)
        assert (tmp_path / "migrator.sqlite").is_file()

    def test_resolve_migrate_url_matches_app(self, tmp_path: Path) -> None:
        assert resolve_migrate_url(tmp_path) == local_sqlite_url(tmp_path)
        explicit = "sqlite:///:memory:"
        assert resolve_migrate_url(tmp_path, explicit) == explicit


class TestUpgradeIdempotentAndLegacy:
    def test_upgrade_twice_is_idempotent(self, tmp_path: Path) -> None:
        url = local_sqlite_url(tmp_path)
        upgrade_head(url)
        upgrade_head(url)
        store = SqliteStateStore(tmp_path)
        try:
            record = store.create(
                JobRecordBuilder().with_id("j1").with_status("pending").build()
            )
            assert store.get("j1").id == record.id
        finally:
            store.close()

    def test_legacy_full_schema_without_alembic_version_is_stamped(
        self, tmp_path: Path
    ) -> None:
        """Pre-Alembic create_all DBs with current columns stamp to head."""
        from src.jobs.persistence.models import METADATA

        db = tmp_path / "migrator.sqlite"
        engine = create_engine_for_url(local_sqlite_url(tmp_path))
        try:
            METADATA.create_all(engine)
        finally:
            engine.dispose()

        conn = sqlite3.connect(str(db))
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "alembic_version" not in tables
            assert {"jobs", "events", "meta"} <= tables
        finally:
            conn.close()

        upgrade_head(local_sqlite_url(tmp_path))
        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            assert version is not None
        finally:
            conn.close()

        store = SqliteStateStore(tmp_path)
        try:
            store.create(
                JobRecordBuilder().with_id("legacy-1").with_status("done").build()
            )
            assert store.get("legacy-1").status == "done"
        finally:
            store.close()

    def test_incomplete_legacy_schema_gains_missing_columns_then_stamps(
        self, tmp_path: Path
    ) -> None:
        """Pre-Alembic DBs missing later columns are altered, then stamped."""
        db = tmp_path / "migrator.sqlite"
        conn = sqlite3.connect(str(db))
        conn.executescript(
            """
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                current INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0,
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

        upgrade_head(local_sqlite_url(tmp_path))
        conn = sqlite3.connect(str(db))
        try:
            assert EXPECTED_JOB_COLUMNS <= _table_columns(conn, "jobs")
            assert EXPECTED_EVENT_COLUMNS <= _table_columns(conn, "events")
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            assert version is not None
        finally:
            conn.close()

        store = SqliteStateStore(tmp_path)
        try:
            assert store.get("old-1").id == "old-1"
            store.save(
                JobRecordBuilder()
                .with_id("old-1")
                .with_status("done")
                .build()
            )
            assert store.get("old-1").status == "done"
        finally:
            store.close()


class TestStoreUsesMigratedSchema:
    def test_sqlite_state_store_boots_via_alembic(self, tmp_path: Path) -> None:
        store = SqliteStateStore(tmp_path)
        try:
            store.create(
                JobRecordBuilder().with_id("boot-1").with_status("pending").build()
            )
            assert store.get("boot-1").id == "boot-1"
            inspector = inspect(store._engine)
            assert set(inspector.get_table_names()) >= {
                "jobs",
                "events",
                "meta",
                "alembic_version",
            }
        finally:
            store.close()

    def test_memory_engine_upgrades_before_use(self, tmp_path: Path) -> None:
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        store = SqlAlchemyStateStore(
            tmp_path,
            engine=engine,
            url="sqlite:///:memory:",
        )
        try:
            store.create(
                JobRecordBuilder().with_id("mem-1").with_status("pending").build()
            )
            assert store.get("mem-1").id == "mem-1"
        finally:
            store.close()


class TestDowngradeUpgradeSmoke:
    def test_downgrade_base_then_upgrade_head(self, tmp_path: Path) -> None:
        from alembic import command

        url = local_sqlite_url(tmp_path)
        upgrade_head(url)
        cfg = alembic_config(url)
        command.downgrade(cfg, "base")

        conn = sqlite3.connect(str(tmp_path / "migrator.sqlite"))
        try:
            names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "jobs" not in names
            assert "events" not in names
            assert "meta" not in names
        finally:
            conn.close()

        upgrade_head(url)
        store = SqliteStateStore(tmp_path)
        try:
            store.create(
                JobRecordBuilder().with_id("after-down").with_status("pending").build()
            )
            assert store.get("after-down").id == "after-down"
        finally:
            store.close()


class TestFailClosed:
    def test_missing_alembic_ini_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "src.jobs.persistence.migrate.alembic_root",
            lambda: tmp_path / "missing-backend",
        )
        with pytest.raises(FileNotFoundError, match="alembic.ini"):
            alembic_config("sqlite:///:memory:")
