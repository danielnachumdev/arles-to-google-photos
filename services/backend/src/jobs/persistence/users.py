"""Users table access: upsert from oauth identity email."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select

from .models import USERS_TABLE

if TYPE_CHECKING:
    from .sqlalchemy_state import SqlAlchemyStateStore


@dataclass(frozen=True)
class UserRecord:
    id: str
    email: str
    created_at: str


class UserStore:
    """Persist users keyed by normalized email (FK target for job owners)."""

    def __init__(self, state: "SqlAlchemyStateStore") -> None:
        self._state = state

    def upsert_email(self, email: str) -> UserRecord:
        normalized = str(email or "").strip().lower()
        if not normalized or "@" not in normalized:
            raise ValueError(f"invalid email: {email!r}")
        with self._state._lock:
            with self._state._engine.begin() as conn:
                row = conn.execute(
                    select(USERS_TABLE).where(USERS_TABLE.c.email == normalized)
                ).mappings().first()
                if row is not None:
                    return UserRecord(
                        id=str(row["id"]),
                        email=str(row["email"]),
                        created_at=str(row["created_at"]),
                    )
                user_id = str(uuid.uuid4())
                created = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    USERS_TABLE.insert().values(
                        id=user_id,
                        email=normalized,
                        created_at=created,
                    )
                )
                self._state._sync_sqlite()
                return UserRecord(id=user_id, email=normalized, created_at=created)

    def get(self, user_id: str) -> UserRecord:
        with self._state._lock:
            with self._state._engine.connect() as conn:
                row = conn.execute(
                    select(USERS_TABLE).where(USERS_TABLE.c.id == user_id)
                ).mappings().first()
        if row is None:
            raise KeyError(user_id)
        return UserRecord(
            id=str(row["id"]),
            email=str(row["email"]),
            created_at=str(row["created_at"]),
        )

    def get_by_email(self, email: str) -> Optional[UserRecord]:
        normalized = str(email or "").strip().lower()
        with self._state._lock:
            with self._state._engine.connect() as conn:
                row = conn.execute(
                    select(USERS_TABLE).where(USERS_TABLE.c.email == normalized)
                ).mappings().first()
        if row is None:
            return None
        return UserRecord(
            id=str(row["id"]),
            email=str(row["email"]),
            created_at=str(row["created_at"]),
        )
