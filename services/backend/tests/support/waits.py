"""Poll job status / orchestrator snapshots without copy-paste loops."""
from __future__ import annotations

import time
from typing import Any, Mapping, Optional

from fastapi.testclient import TestClient

from src.jobs.orchestrator import JobOrchestrator
from src.jobs.store import JobStore


class JobWaiter:
    """Wait until a job or orchestrator snapshot reaches a target state."""

    def __init__(self, *, timeout: float = 8.0, interval: float = 0.02) -> None:
        self._timeout = timeout
        self._interval = interval

    def http_status(
        self,
        client: TestClient,
        job_id: str,
        *,
        status: str = "done",
        last_stage: Optional[str] = None,
        last_stages: Optional[frozenset[str] | set[str] | tuple[str, ...]] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        accepted = None
        if last_stages is not None:
            accepted = frozenset(last_stages)
        elif last_stage is not None:
            accepted = frozenset({last_stage})
        deadline = time.monotonic() + (timeout if timeout is not None else self._timeout)
        last = None
        while time.monotonic() < deadline:
            last = client.get(f"/api/jobs/{job_id}")
            if last.status_code == 200:
                body = last.json()
                if body.get("status") == status and (
                    accepted is None or body.get("last_stage") in accepted
                ):
                    return body
            time.sleep(self._interval)
        detail = last.text if last is not None else "no response"
        want = status if accepted is None else f"{status}/{sorted(accepted)}"
        raise AssertionError(f"job {job_id} did not reach {want}: {detail}")

    def store_status(
        self,
        store: JobStore,
        job_id: str,
        status: str,
        *,
        timeout: Optional[float] = None,
    ) -> None:
        deadline = time.monotonic() + (timeout if timeout is not None else self._timeout)
        last = None
        while time.monotonic() < deadline:
            last = store.get(job_id).status
            if last == status:
                return
            time.sleep(self._interval)
        raise AssertionError(
            f"job {job_id} status {last!r} did not become {status!r}"
        )

    def snapshot(
        self,
        orch: JobOrchestrator,
        key: str,
        *,
        minimum: int = 1,
        timeout: Optional[float] = None,
    ) -> Mapping[str, Any]:
        deadline = time.monotonic() + (timeout if timeout is not None else self._timeout)
        last = None
        while time.monotonic() < deadline:
            snap = orch.snapshot()
            last = snap.get(key)
            if isinstance(last, int) and last >= minimum:
                return snap
            time.sleep(self._interval)
        raise AssertionError(f"orchestrator {key}={last!r} did not reach {minimum}")
