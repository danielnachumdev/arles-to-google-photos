"""In-memory Google access tokens keyed by job id. Never written to disk."""
from __future__ import annotations

import threading
from typing import Dict, Optional


class AccessTokenVault:
    """Hold short-lived Google Photos tokens until preview is ready."""

    def __init__(self) -> None:
        self._tokens: Dict[str, str] = {}
        self._lock = threading.Lock()

    def put(self, job_id: str, token: str) -> None:
        cleaned = (token or "").strip()
        if not cleaned or not job_id:
            return
        with self._lock:
            self._tokens[str(job_id)] = cleaned

    def pop(self, job_id: str) -> Optional[str]:
        with self._lock:
            return self._tokens.pop(str(job_id), None)

    def discard(self, job_id: str) -> None:
        with self._lock:
            self._tokens.pop(str(job_id), None)

    def get(self, job_id: str) -> Optional[str]:
        with self._lock:
            return self._tokens.get(str(job_id))
