"""Job persistence: StateStore (records) + ArtifactStore (album files).

Cloud vs local is ``APP_ENV`` (not bucket presence):

- Unset / blank ``APP_ENV`` → **cloud** (aliases: ``prod``, ``production``).
- ``local`` (aliases: ``dev``, ``development``) → compose / host volume flow.
- ``GCS_BUCKET`` / ``DATABASE_URL`` are resource addresses, not the detector.

**Cloud:** ``GcsArtifactStore`` (``GCS_BUCKET`` / ``ARTIFACT_BUCKET`` required).
``DATABASE_URL`` optional (SQLAlchemy Postgres / Cloud SQL); if unset → local
sqlite **plus** GCS sqlite mirror. ``gs://`` / ``gcs://`` ``DATABASE_URL`` is
rejected.

**Local:** ``FsArtifactStore`` on ``JOBS_ROOT``; local sqlite (or json). Ignore
``GCS_BUCKET`` for backend selection (no GCS artifacts / sqlite mirror).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from .artifacts import ArtifactStore
from .paths import normalize_gcs_bucket, normalize_gcs_prefix, parse_gcs_uri
from .state import JobRecord, StateStore

__all__ = [
    "ArtifactStore",
    "FsArtifactStore",
    "GcsArtifactStore",
    "GcsSqliteMirror",
    "JobRecord",
    "JsonStateStore",
    "SqlAlchemyStateStore",
    "SqliteStateStore",
    "StateStore",
    "build_artifact_store",
    "build_state_store",
    "local_sqlite_url",
    "reject_gcs_database_url",
    "resolve_app_env",
    "resolve_artifact_bucket",
    "resolve_database_url",
    "resolve_gcs_prefix",
    "sqlite_gcs_object_key",
]

_CLOUD_ALIASES = frozenset({"cloud", "prod", "production"})
_LOCAL_ALIASES = frozenset({"local", "dev", "development"})
_CLOUD_BUCKET_REQUIRED = (
    "APP_ENV is cloud: GCS_BUCKET (or ARTIFACT_BUCKET) is required. "
    "Set APP_ENV=local for filesystem artifacts on JOBS_ROOT."
)


def _env_first(*names: str) -> str:
    for name in names:
        value = str(os.environ.get(name, "") or "").strip()
        if value:
            return value
    return ""


def local_sqlite_url(base_dir: Path) -> str:
    from .sqlalchemy_state import local_sqlite_url as _local_sqlite_url

    return _local_sqlite_url(base_dir)


def resolve_app_env(value: Optional[str] = None) -> str:
    """Return ``cloud`` or ``local``. Unset / blank → ``cloud``."""
    if value is None:
        text = str(os.environ.get("APP_ENV", "") or "").strip().lower()
    else:
        text = str(value).strip().lower()
    if not text:
        return "cloud"
    if text in _CLOUD_ALIASES:
        return "cloud"
    if text in _LOCAL_ALIASES:
        return "local"
    raise ValueError(
        "APP_ENV must be cloud (aliases: prod, production) or local "
        f"(aliases: dev, development); got {text!r}"
    )


def resolve_database_url(base_dir: Path, url: Optional[str] = None) -> str:
    """Explicit ``url`` wins; else ``DATABASE_URL`` / ``SQLALCHEMY_DATABASE_URL``; else local sqlite."""
    from .sqlalchemy_state import reject_gcs_database_url

    if url is not None:
        text = str(url).strip()
        if text:
            reject_gcs_database_url(text)
            return text
        return local_sqlite_url(base_dir)
    found = _env_first("DATABASE_URL", "SQLALCHEMY_DATABASE_URL")
    if found:
        reject_gcs_database_url(found)
        return found
    return local_sqlite_url(base_dir)


def resolve_artifact_bucket(bucket: Optional[str] = None) -> str:
    """Explicit ``bucket`` wins; else ``GCS_BUCKET`` / ``ARTIFACT_BUCKET``; else blank."""
    if bucket is not None:
        return str(bucket).strip()
    return _env_first("GCS_BUCKET", "ARTIFACT_BUCKET")


def resolve_gcs_prefix(
    bucket_raw: str = "",
    prefix: Optional[str] = None,
) -> str:
    """Object prefix. Explicit ``prefix`` wins; else URI path; else ``GCS_PREFIX``; else ``jobs``."""
    uri_prefix = ""
    text = str(bucket_raw or "").strip()
    lowered = text.lower()
    if lowered.startswith("gcs://") or lowered.startswith("gs://"):
        _bucket, uri_prefix = parse_gcs_uri(text)
    if prefix is not None:
        return normalize_gcs_prefix(prefix)
    if uri_prefix:
        return normalize_gcs_prefix(uri_prefix)
    if "GCS_PREFIX" in os.environ:
        return normalize_gcs_prefix(os.environ["GCS_PREFIX"])
    return "jobs"


def _bucket_name_from_raw(raw: str) -> str:
    lowered = str(raw).strip().lower()
    if lowered.startswith("gcs://") or lowered.startswith("gs://"):
        bucket, _prefix = parse_gcs_uri(raw)
        return bucket
    return normalize_gcs_bucket(raw)


def build_state_store(
    base_dir: Path,
    url: Optional[str] = None,
    *,
    engine: Any = None,
    use_json: bool = False,
    gcs_client: Any = None,
    gcs_bucket: Optional[str] = None,
    gcs_prefix: Optional[str] = None,
) -> StateStore:
    if use_json:
        from .json_state import JsonStateStore

        return JsonStateStore(base_dir)
    from .sqlalchemy_state import DB_NAME, SqlAlchemyStateStore
    from .gcs_sqlite import GcsSqliteMirror

    resolved = resolve_database_url(base_dir, url)
    mirror = None
    journal_mode = None
    if resolve_app_env() == "cloud" and engine is None and resolved == local_sqlite_url(
        base_dir
    ):
        bucket_raw = resolve_artifact_bucket(gcs_bucket)
        if not bucket_raw:
            raise ValueError(_CLOUD_BUCKET_REQUIRED)
        mirror = GcsSqliteMirror(
            Path(base_dir) / DB_NAME,
            bucket=_bucket_name_from_raw(bucket_raw),
            prefix=resolve_gcs_prefix(bucket_raw, gcs_prefix),
            client=gcs_client,
        )
        journal_mode = "DELETE"
    return SqlAlchemyStateStore(
        base_dir,
        url=resolved,
        engine=engine,
        sqlite_mirror=mirror,
        journal_mode=journal_mode,
    )


def build_artifact_store(
    base_dir: Path,
    bucket: Optional[str] = None,
    *,
    prefix: Optional[str] = None,
    client: Any = None,
) -> ArtifactStore:
    if resolve_app_env() == "local":
        from .fs_artifacts import FsArtifactStore

        return FsArtifactStore(base_dir)
    raw = resolve_artifact_bucket(bucket)
    if not raw:
        raise ValueError(_CLOUD_BUCKET_REQUIRED)
    from .gcs_artifacts import GcsArtifactStore

    return GcsArtifactStore(
        base_dir,
        bucket=_bucket_name_from_raw(raw),
        prefix=resolve_gcs_prefix(raw, prefix),
        client=client,
    )


def __getattr__(name: str) -> Any:
    if name == "JsonStateStore":
        from .json_state import JsonStateStore

        return JsonStateStore
    if name == "SqlAlchemyStateStore":
        from .sqlalchemy_state import SqlAlchemyStateStore

        return SqlAlchemyStateStore
    if name == "SqliteStateStore":
        from .sqlalchemy_state import SqliteStateStore

        return SqliteStateStore
    if name == "FsArtifactStore":
        from .fs_artifacts import FsArtifactStore

        return FsArtifactStore
    if name == "GcsArtifactStore":
        from .gcs_artifacts import GcsArtifactStore

        return GcsArtifactStore
    if name == "GcsSqliteMirror":
        from .gcs_sqlite import GcsSqliteMirror

        return GcsSqliteMirror
    if name == "sqlite_gcs_object_key":
        from .gcs_sqlite import sqlite_gcs_object_key

        return sqlite_gcs_object_key
    if name == "reject_gcs_database_url":
        from .sqlalchemy_state import reject_gcs_database_url

        return reject_gcs_database_url
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
