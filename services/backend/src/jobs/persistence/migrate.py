"""Apply Alembic migrations against the app database URL / engine.

Fail closed: migration errors raise and prevent store construction / app boot.
Existing sqlite files created before Alembic (via ``create_all``) are stamped
to head when ``jobs`` / ``events`` / ``meta`` already exist and there is no
``alembic_version`` row, so upgrade is a no-op for the current schema.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Union

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Float, Integer, inspect, text
from sqlalchemy.engine import Connection, Engine

_REQUIRED_TABLES = frozenset({"jobs", "events", "meta"})


def alembic_root() -> Path:
    """Directory that contains ``alembic.ini`` (``services/backend`` / Docker ``/app``).

    Resolution order:
    1. ``ALEMBIC_ROOT`` env
    2. Dev layout: ``…/backend/src/jobs/persistence/migrate.py`` → ``backend``
    3. Process CWD (Docker / Cloud Run ``WORKDIR=/app`` with copied assets)
    """
    env = str(os.environ.get("ALEMBIC_ROOT", "") or "").strip()
    if env:
        return Path(env)
    candidate = Path(__file__).resolve().parents[3]
    if (candidate / "alembic.ini").is_file():
        return candidate
    cwd = Path.cwd()
    if (cwd / "alembic.ini").is_file():
        return cwd
    raise FileNotFoundError(
        "alembic.ini not found (set ALEMBIC_ROOT or ship alembic.ini next to CWD)"
    )


def alembic_config(url: str) -> Config:
    root = alembic_root()
    ini_path = root / "alembic.ini"
    if not ini_path.is_file():
        raise FileNotFoundError(f"alembic.ini not found at {ini_path}")
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", str(url).strip())
    return cfg


def resolve_migrate_url(
    base_dir: Path,
    url: Optional[str] = None,
) -> str:
    """Same resolution as the app: explicit URL, else env, else local sqlite."""
    from . import resolve_database_url
    from .sqlalchemy_state import local_sqlite_url, reject_gcs_database_url

    if url is not None:
        text_url = str(url).strip()
        if text_url:
            reject_gcs_database_url(text_url)
            return text_url
        return local_sqlite_url(base_dir)
    return resolve_database_url(base_dir, None)


def _tables_present(conn: Connection) -> bool:
    names = set(inspect(conn).get_table_names())
    return _REQUIRED_TABLES.issubset(names)


def _expected_columns() -> dict[str, frozenset[str]]:
    """Columns belonging to revision ``001_initial_schema`` (legacy bridge)."""
    from .models import EVENTS_TABLE, JOBS_TABLE, META_TABLE

    skip = frozenset({"owner_id"})
    return {
        "jobs": frozenset(c.name for c in JOBS_TABLE.columns if c.name not in skip),
        "events": frozenset(
            c.name for c in EVENTS_TABLE.columns if c.name not in skip
        ),
        "meta": frozenset(c.name for c in META_TABLE.columns),
    }


def _missing_columns(conn: Connection) -> list[str]:
    inspector = inspect(conn)
    missing: list[str] = []
    for table, expected in _expected_columns().items():
        if table not in inspector.get_table_names():
            continue
        present = {str(col["name"]) for col in inspector.get_columns(table)}
        for name in sorted(expected - present):
            missing.append(f"{table}.{name}")
    return missing


def _sqlite_add_column_ddl(column: Any) -> str:
    """SQLite ``ALTER TABLE … ADD COLUMN`` type + default fragment."""
    if isinstance(column.type, Float):
        type_sql = "REAL"
    elif isinstance(column.type, Integer):
        type_sql = "INTEGER"
    else:
        type_sql = "TEXT"
    if column.server_default is not None:
        default = column.server_default.arg
        if hasattr(default, "text"):
            default = default.text
        return f"{type_sql} NOT NULL DEFAULT {default}"
    return type_sql


def _ensure_legacy_columns(connection: Connection) -> None:
    """Add columns missing from pre-Alembic DBs (one-time bridge before stamp)."""
    from .models import EVENTS_TABLE, JOBS_TABLE, META_TABLE

    skip = frozenset({"owner_id"})
    inspector = inspect(connection)
    for table in (JOBS_TABLE, EVENTS_TABLE, META_TABLE):
        name = table.name
        if name not in inspector.get_table_names():
            continue
        present = {str(col["name"]) for col in inspector.get_columns(name)}
        for column in table.columns:
            if column.name in present or column.primary_key or column.name in skip:
                continue
            ddl = _sqlite_add_column_ddl(column)
            connection.execute(
                text(f"ALTER TABLE {name} ADD COLUMN {column.name} {ddl}")
            )


def _current_revision(conn: Connection) -> Optional[str]:
    context = MigrationContext.configure(conn)
    return context.get_current_revision()


def _stamp_existing_schema(connection: Connection, cfg: Config) -> None:
    """Stamp legacy create_all schema so ``upgrade head`` can continue.

    - Schema already has ``users`` (METADATA.create_all with current models) →
      stamp **head** (002 already applied in practice).
    - Otherwise stamp ``001_initial_schema`` so 002 still runs. Incomplete 001
      columns are altered first (sqlite bridge). No fake owner seed.
    """
    if _current_revision(connection) is not None:
        return
    if not _tables_present(connection):
        return
    if _missing_columns(connection):
        _ensure_legacy_columns(connection)
        still_missing = _missing_columns(connection)
        if still_missing:
            raise RuntimeError(
                "incomplete legacy schema after column bridge: missing column(s): "
                + ", ".join(still_missing)
            )
    script = ScriptDirectory.from_config(cfg)
    context = MigrationContext.configure(connection)
    inspector = inspect(connection)
    if "users" in set(inspector.get_table_names()):
        head = script.get_current_head()
        if head is None:
            raise RuntimeError("no Alembic head revision found")
        context.stamp(script, head)
        return
    initial = "001_initial_schema"
    if script.get_revision(initial) is None:
        raise RuntimeError(f"missing Alembic revision {initial}")
    context.stamp(script, initial)


def upgrade_head(
    url_or_engine: Union[str, Engine],
    *,
    journal_mode: str = "WAL",
) -> None:
    """Upgrade the database to Alembic head. Raises on failure (fail closed)."""
    from .sqlalchemy_state import create_engine_for_url, reject_gcs_database_url

    owns_engine = False
    if isinstance(url_or_engine, Engine):
        engine = url_or_engine
        url = str(engine.url)
    else:
        url = str(url_or_engine).strip()
        reject_gcs_database_url(url)
        engine = create_engine_for_url(url, journal_mode=journal_mode)
        owns_engine = True
    try:
        cfg = alembic_config(url)

        def _upgrade(connection: Connection) -> None:
            _stamp_existing_schema(connection, cfg)
            cfg.attributes["connection"] = connection
            try:
                command.upgrade(cfg, "head")
            finally:
                cfg.attributes.pop("connection", None)

        with engine.begin() as conn:
            _upgrade(conn)
    finally:
        if owns_engine:
            engine.dispose()


def upgrade_jobs_root(
    base_dir: Path,
    url: Optional[str] = None,
    *,
    journal_mode: Optional[str] = None,
) -> str:
    """Resolve URL under ``base_dir``, run migrations, return the URL used."""
    Path(base_dir).mkdir(parents=True, exist_ok=True)
    resolved = resolve_migrate_url(base_dir, url)
    mode = journal_mode or "WAL"
    upgrade_head(resolved, journal_mode=mode)
    return resolved
