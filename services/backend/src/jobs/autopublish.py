"""Start a child upload after preview when auto_publish was requested at job start."""
from __future__ import annotations

from typing import Optional

from .cancel import store_is_cancelled
from .events import JobEventBus
from .publish import PublishService
from .store import STATUS_CANCELLED, STATUS_FAILED, JobNotFoundError, JobStore
from .tokens import AccessTokenVault


class AutoPublisher:
    """Remember an in-memory token and launch publish after preview_ready."""

    def __init__(
        self,
        store: JobStore,
        publish: PublishService,
        events: JobEventBus,
        vault: Optional[AccessTokenVault] = None,
    ) -> None:
        self._store = store
        self._publish = publish
        self._events = events
        self._vault = vault or AccessTokenVault()

    def remember(self, job_id: str, token: str) -> None:
        self._vault.put(job_id, token)

    def discard(self, job_id: str) -> None:
        self._vault.discard(job_id)

    def after_preview(
        self,
        preview_id: str,
        *,
        parent_id: str,
        token_key: str,
    ) -> Optional[str]:
        try:
            preview = self._store.get(preview_id)
            parent = self._store.get(parent_id)
        except JobNotFoundError:
            self._vault.discard(token_key)
            return None
        flagged = bool(
            parent.auto_publish or preview.auto_publish or self._vault.get(token_key)
        )
        if not flagged:
            self._vault.discard(token_key)
            return None
        if store_is_cancelled(self._store, preview_id) or store_is_cancelled(
            self._store, parent_id
        ):
            self._vault.discard(token_key)
            return None
        if preview.status in (STATUS_CANCELLED, STATUS_FAILED):
            self._vault.discard(token_key)
            return None
        if parent.status == STATUS_CANCELLED:
            self._vault.discard(token_key)
            return None
        if preview.preview is None or not preview.preview.items:
            self._vault.discard(token_key)
            return None
        token = self._vault.pop(token_key)
        if not token:
            self._events.emit(
                parent_id,
                "auto_publish",
                "skipped: access token unavailable",
            )
            return None
        try:
            return self._publish.launch(
                preview_id,
                access_token=token,
                parent_job_id=parent_id,
            )
        except Exception as exc:
            self._events.emit(
                parent_id,
                "auto_publish",
                f"failed: {exc}",
            )
            return None
