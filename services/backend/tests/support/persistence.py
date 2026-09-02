"""Strategy pattern: json vs SQLAlchemy StateStore backends for contract tests."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Sequence

from src.jobs.persistence.json_state import JsonStateStore
from src.jobs.persistence.sqlalchemy_state import SqlAlchemyStateStore
from src.jobs.persistence.sqlite_state import SqliteStateStore
from src.jobs.persistence.state import StateStore


class StateStoreBackend(ABC):
    """Construct a StateStore under a temp root. Name is used in pytest ids."""

    name: str

    @abstractmethod
    def create(self, tmp_path: Path) -> StateStore:
        raise NotImplementedError


class JsonStateStoreBackend(StateStoreBackend):
    name = "json"

    def create(self, tmp_path: Path) -> StateStore:
        return JsonStateStore(tmp_path)


class SqliteStateStoreBackend(StateStoreBackend):
    name = "sqlite"

    def create(self, tmp_path: Path) -> StateStore:
        return SqliteStateStore(tmp_path)


class SqlAlchemyUrlStateStoreBackend(StateStoreBackend):
    """Same SQLAlchemy store via an explicit sqlite URL (fake remote)."""

    name = "sqlalchemy-url"

    def create(self, tmp_path: Path) -> StateStore:
        db = tmp_path / "remote.sqlite"
        return SqlAlchemyStateStore(
            tmp_path,
            url="sqlite:///" + db.resolve().as_posix(),
        )


def state_store_backends() -> Sequence[StateStoreBackend]:
    return (
        JsonStateStoreBackend(),
        SqliteStateStoreBackend(),
        SqlAlchemyUrlStateStoreBackend(),
    )
