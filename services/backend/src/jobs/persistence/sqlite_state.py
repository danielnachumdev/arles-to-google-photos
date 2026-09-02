"""Backward-compatible alias: local SQLAlchemy sqlite under ``JOBS_ROOT``."""
from __future__ import annotations

from .sqlalchemy_state import DB_NAME, SqlAlchemyStateStore as SqliteStateStore

__all__ = ["DB_NAME", "SqliteStateStore"]
