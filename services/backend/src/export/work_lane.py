"""Generic adaptive parallel work lane with shared cooldown on transient failures.

One instance per usage (e.g. remote host vs Google Photos). Callers submit
callables; workers share a lane-wide pause so a transient failure sleeps the
whole lane together before the next attempt.
"""
from __future__ import annotations

import random
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Generic, Iterable, List, Optional, TypeVar

T = TypeVar("T")

IsTransient = Callable[[BaseException], bool]


class TransientError(Exception):
    """Default transient signal callers may raise from submitted work."""


def _default_is_transient(exc: BaseException) -> bool:
    return isinstance(exc, TransientError)


class AdaptiveWorkLane(Generic[T]):
    """Run callables with bounded parallelism and adaptive shared cooldown."""

    def __init__(
        self,
        *,
        max_workers: int = 8,
        min_workers: int = 1,
        initial_backoff_s: float = 1.0,
        max_backoff_s: float = 60.0,
        max_retries: int = 5,
        is_transient: Optional[IsTransient] = None,
        success_streak_to_restore: int = 8,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        if min_workers < 1 or min_workers > max_workers:
            raise ValueError("min_workers must be in 1..max_workers")
        self._max_workers = int(max_workers)
        self._min_workers = int(min_workers)
        self._initial_backoff_s = float(initial_backoff_s)
        self._max_backoff_s = float(max_backoff_s)
        self._max_retries = int(max_retries)
        self._is_transient = is_transient or _default_is_transient
        self._success_streak_to_restore = max(1, int(success_streak_to_restore))

        self._lock = threading.Condition()
        self._paused_until = 0.0
        self._backoff_s = self._initial_backoff_s
        self._active_cap = self._max_workers
        self._running = 0
        self._success_streak = 0
        self._closed = False
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="work-lane",
        )

    def submit(self, fn: Callable[[], T]) -> Future[T]:
        if self._closed:
            raise RuntimeError("AdaptiveWorkLane is closed")
        return self._executor.submit(self._execute, fn)

    def run(self, fn: Callable[[], T]) -> T:
        return self.submit(fn).result()

    def map(self, fns: Iterable[Callable[[], T]]) -> List[T]:
        tasks = list(fns)
        futures = [self.submit(fn) for fn in tasks]
        return [future.result() for future in futures]

    def close(self, *, wait: bool = True) -> None:
        with self._lock:
            self._closed = True
            self._lock.notify_all()
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def __enter__(self) -> "AdaptiveWorkLane[T]":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close(wait=True)

    def _execute(self, fn: Callable[[], T]) -> T:
        attempt = 0
        while True:
            # Wait out shared cooldown without holding a worker slot so the
            # whole lane idles together after a transient trip.
            self._wait_cooldown()
            self._acquire_slot()
            try:
                if self._cooldown_remaining() > 0:
                    continue
                try:
                    result = fn()
                except BaseException as exc:
                    if self._is_transient(exc) and attempt < self._max_retries:
                        attempt += 1
                        self._trip_cooldown()
                        continue
                    if self._is_transient(exc):
                        self._trip_cooldown()
                    raise
                self._on_success()
                return result
            finally:
                self._release_slot()

    def _acquire_slot(self) -> None:
        with self._lock:
            while True:
                if self._closed:
                    raise RuntimeError("AdaptiveWorkLane is closed")
                if self._running < self._active_cap:
                    self._running += 1
                    return
                self._lock.wait(timeout=0.05)

    def _release_slot(self) -> None:
        with self._lock:
            self._running = max(0, self._running - 1)
            self._lock.notify_all()

    def _cooldown_remaining(self) -> float:
        with self._lock:
            return max(0.0, self._paused_until - time.monotonic())

    def _wait_cooldown(self) -> None:
        with self._lock:
            while True:
                remaining = self._paused_until - time.monotonic()
                if remaining <= 0:
                    return
                self._lock.wait(timeout=remaining)

    def _trip_cooldown(self) -> None:
        with self._lock:
            delay = self._backoff_s * (0.8 + 0.4 * random.random())
            delay = min(delay, self._max_backoff_s)
            self._paused_until = max(
                self._paused_until, time.monotonic() + delay
            )
            self._backoff_s = min(
                self._backoff_s * 2.0, self._max_backoff_s
            )
            self._active_cap = max(self._min_workers, self._active_cap // 2)
            self._success_streak = 0
            self._lock.notify_all()

    def _on_success(self) -> None:
        with self._lock:
            self._success_streak += 1
            self._backoff_s = self._initial_backoff_s
            if (
                self._success_streak >= self._success_streak_to_restore
                and self._active_cap < self._max_workers
            ):
                self._active_cap = min(
                    self._max_workers, self._active_cap + 1
                )
                self._success_streak = 0
                self._lock.notify_all()
