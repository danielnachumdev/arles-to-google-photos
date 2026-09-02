"""Cancel in-progress jobs: store flag + SSE, without deleting artifacts."""
from __future__ import annotations

from typing import Any, Callable, List, Optional

from ..progress import CancellableProgressSink, JobCancelled, ProgressSink
from .events import JobEventBus
from .store import Job, JobStore, STATUS_CANCELLED

__all__ = [
    "CancelService",
    "JobCancelled",
    "cancellable_sink",
    "store_is_cancelled",
]


def store_is_cancelled(store: Any, job_id: str) -> bool:
    """True only when ``store.is_cancelled`` returns exact ``True`` (not a mock)."""
    checker = getattr(store, "is_cancelled", None)
    if not callable(checker):
        return False
    return checker(job_id) is True


def cancellable_sink(inner: ProgressSink, store: Any, job_id: str) -> ProgressSink:
    return CancellableProgressSink(
        inner, lambda: store_is_cancelled(store, job_id)
    )


class CancelService:
    """Request cooperative cancel and emit a distinct SSE ``cancelled`` stage."""

    def __init__(
        self,
        store: JobStore,
        events: JobEventBus,
        drop_pending: Optional[Callable[[str], bool]] = None,
        on_settled: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._store = store
        self._events = events
        self._drop_pending = drop_pending
        self._on_settled = on_settled

    def cancel(self, job_id: str) -> Job:
        cancelled_ids = self._store.request_cancel(job_id)
        if self._drop_pending is not None:
            for cid in cancelled_ids:
                self._drop_pending(cid)
        for cid in cancelled_ids:
            self._events.emit(cid, "cancelled", "Job cancelled")
        if self._on_settled is not None:
            self._on_settled(job_id)
        return self._store.get(job_id)

    def ensure_cancelled(self, job_id: str, job_type: str) -> List[str]:
        """Idempotent worker-side mark: status + SSE if not already cancelled."""
        newly: List[str] = []
        job = self._store.get(job_id)
        if job.status != STATUS_CANCELLED:
            self._store.set_status(job_id, STATUS_CANCELLED, job_type=job_type)
            self._events.emit(job_id, "cancelled", "Job cancelled")
            newly.append(job_id)
        for child in self._store.list_cancellable_descendants(job_id):
            if self._store.cancel_if_running(child.id):
                self._events.emit(child.id, "cancelled", "Job cancelled")
                newly.append(child.id)
        return newly
