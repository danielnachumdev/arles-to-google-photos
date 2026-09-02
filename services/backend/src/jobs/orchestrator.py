"""FIFO job queue: pending vs running vs waiting, with a cap on running only."""
from __future__ import annotations

import threading
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Protocol, Set

from .store import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_WAITING,
    JobStore,
)

DEFAULT_MAX_CONCURRENT = 3
MIN_CONCURRENT = 1
MAX_CONCURRENT = 32
META_MAX_CONCURRENT_KEY = "max_concurrent_jobs"
INTERRUPTED_ERROR = "interrupted"
INTERRUPTED_ERROR_CODE = "interrupted"

WorkFn = Callable[[], None]


class _EventBusLike(Protocol):
    def emit(
        self,
        job_id: str,
        stage: str,
        message: str = "",
        *,
        current: int = 0,
        total: int = 0,
        extra: Optional[Any] = None,
        kind: Optional[str] = None,
        audience: Optional[str] = None,
    ) -> None:
        ...


def validate_max_concurrent(value: object) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("max_concurrent_jobs must be an integer") from exc
    if parsed < MIN_CONCURRENT or parsed > MAX_CONCURRENT:
        raise ValueError(
            f"max_concurrent_jobs must be between {MIN_CONCURRENT} and {MAX_CONCURRENT}"
        )
    return parsed


class JobOrchestrator:
    """Thread-safe pending queue + running set + waiting set.

    Only ``running`` jobs count toward ``max_concurrent``.
    """

    def __init__(
        self,
        store: JobStore,
        *,
        max_concurrent: Optional[int] = None,
        events: Optional[_EventBusLike] = None,
    ) -> None:
        self._store = store
        self._events = events
        self._lock = threading.Lock()
        self._pending: Deque[str] = deque()
        self._fns: Dict[str, WorkFn] = {}
        self._running: Set[str] = set()
        self._waiting: Set[str] = set()
        loaded = max_concurrent
        if loaded is None:
            loaded = self._load_persisted_max()
        self._max_concurrent = validate_max_concurrent(
            DEFAULT_MAX_CONCURRENT if loaded is None else loaded
        )

    def _load_persisted_max(self) -> Optional[int]:
        getter = getattr(self._store, "get_meta", None)
        if not callable(getter):
            return None
        raw = getter(META_MAX_CONCURRENT_KEY)
        if raw is None or str(raw).strip() == "":
            return None
        try:
            return validate_max_concurrent(raw)
        except ValueError:
            return None

    def persist_max_concurrent(self) -> None:
        setter = getattr(self._store, "set_meta", None)
        if not callable(setter):
            return
        setter(META_MAX_CONCURRENT_KEY, str(self._max_concurrent))

    @property
    def max_concurrent(self) -> int:
        with self._lock:
            return self._max_concurrent

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            pending_ids = list(self._pending)
            running_ids = list(self._running)
            waiting_ids = list(self._waiting)
            max_concurrent = self._max_concurrent
        return {
            "max_concurrent_jobs": max_concurrent,
            "pending": len(pending_ids),
            "running": len(running_ids),
            "waiting": len(waiting_ids),
            "pending_ids": pending_ids,
            "running_ids": running_ids,
            "waiting_ids": waiting_ids,
        }

    def fail_interrupted(self) -> List[str]:
        """Mark leftover ``running`` / ``waiting`` jobs failed after a crash."""
        failed: List[str] = []
        for job in self._store.list():
            if job.status not in (STATUS_RUNNING, STATUS_WAITING):
                continue
            self._store.set_status(
                job.id,
                STATUS_FAILED,
                error=INTERRUPTED_ERROR,
                error_code=INTERRUPTED_ERROR_CODE,
                job_type=job.type,
            )
            failed.append(job.id)
        return failed

    def submit(self, job_id: str, fn: WorkFn) -> None:
        with self._lock:
            if job_id in self._fns or job_id in self._running:
                return
            try:
                job = self._store.get(job_id)
            except Exception:
                return
            if job.status != STATUS_PENDING:
                self._store.set_status(job_id, STATUS_PENDING, job_type=job.type)
            self._pending.append(job_id)
            self._fns[job_id] = fn
        self._pump()

    def drop(self, job_id: str) -> bool:
        """Remove a pending/waiting job so ``fn`` never runs (or is forgotten).

        No-op if already running. Waiting jobs are dropped from the waiting set.
        """
        with self._lock:
            if job_id in self._running:
                return False
            fn = self._fns.pop(job_id, None)
            in_pending = job_id in self._pending
            in_waiting = job_id in self._waiting
            if fn is None and not in_pending and not in_waiting:
                return False
            self._pending = deque(item for item in self._pending if item != job_id)
            self._waiting.discard(job_id)
            return True

    def set_max_concurrent(self, value: int) -> int:
        parsed = validate_max_concurrent(value)
        with self._lock:
            self._max_concurrent = parsed
        self.persist_max_concurrent()
        self._pump()
        return parsed

    def on_child_settled(self, job_id: str) -> None:
        """Re-evaluate waiting ancestors after a child becomes terminal or waiting."""
        self._notify_ancestors(job_id)
        self._pump()

    def _pump(self) -> None:
        to_start: List[tuple[str, WorkFn]] = []
        with self._lock:
            while self._pending and len(self._running) < self._max_concurrent:
                job_id = self._pending.popleft()
                fn = self._fns.get(job_id)
                if fn is None:
                    continue
                if self._store.is_cancelled(job_id):
                    self._fns.pop(job_id, None)
                    continue
                self._running.add(job_id)
                to_start.append((job_id, fn))
        for job_id, fn in to_start:
            thread = threading.Thread(
                target=self._run,
                args=(job_id, fn),
                name=f"job-{job_id}",
                daemon=True,
            )
            thread.start()

    def _run(self, job_id: str, fn: WorkFn) -> None:
        try:
            if self._store.is_cancelled(job_id):
                return
            try:
                job = self._store.get(job_id)
            except Exception:
                return
            if job.status == STATUS_PENDING:
                self._store.set_status(job_id, STATUS_RUNNING, job_type=job.type)
            fn()
        except Exception:
            return
        finally:
            with self._lock:
                self._running.discard(job_id)
                self._fns.pop(job_id, None)
            self._settle_job(job_id)
            self._pump()

    def _still_executing(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._running

    def _settle_job(self, job_id: str) -> None:
        if self._still_executing(job_id):
            return
        try:
            job = self._store.get(job_id)
        except Exception:
            with self._lock:
                self._waiting.discard(job_id)
            return
        if job.status == STATUS_CANCELLED:
            with self._lock:
                self._waiting.discard(job_id)
            self._notify_ancestors(job_id)
            return
        if job.status == STATUS_FAILED:
            with self._lock:
                self._waiting.discard(job_id)
            self._notify_ancestors(job_id)
            return
        if self._store.has_active_descendants(job_id):
            # Track in `_waiting` before flipping store status so snapshot counts
            # never lag behind a `status=waiting` observation (xdist flake).
            with self._lock:
                self._waiting.add(job_id)
            if job.status != STATUS_WAITING:
                self._store.set_status(
                    job_id, STATUS_WAITING, job_type=job.type, warnings=[]
                )
                self._emit(job_id, "waiting")
            return
        with self._lock:
            self._waiting.discard(job_id)
        warnings = self._store.descendant_completion_warnings(job_id)
        already_done = job.status == STATUS_DONE
        if job.status in (STATUS_RUNNING, STATUS_WAITING) or (
            already_done and warnings
        ):
            self._store.set_status(
                job_id,
                STATUS_DONE,
                job_type=job.type,
                warnings=warnings,
            )
            if not already_done:
                self._emit(job_id, "done")
        self._notify_ancestors(job_id)

    def _notify_ancestors(self, job_id: str) -> None:
        try:
            job = self._store.get(job_id)
        except Exception:
            return
        parent_id = job.parent_job_id
        seen: Set[str] = set()
        while parent_id and parent_id not in seen:
            seen.add(parent_id)
            try:
                parent = self._store.get(parent_id)
            except Exception:
                return
            if parent.status == STATUS_WAITING or (
                parent.status == STATUS_RUNNING and not self._still_executing(parent_id)
            ):
                self._settle_job(parent_id)
            parent_id = parent.parent_job_id

    def _emit(self, job_id: str, stage: str, message: str = "") -> None:
        if self._events is None:
            return
        self._events.emit(job_id, stage, message)
