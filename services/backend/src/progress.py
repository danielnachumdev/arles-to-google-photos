"""Progress reporting shared by parser, publisher, scrape, and SSE."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence


class JobCancelled(Exception):
    """Worker stopped because the job was cancelled."""


class ProgressSink(Protocol):
    def emit(
        self,
        stage: str,
        message: str = "",
        *,
        current: int = 0,
        total: int = 0,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        ...


def raise_if_cancelled(sink: Any) -> None:
    """Raise ``JobCancelled`` when ``sink`` is a cancellable wrapper that tripped."""
    check = getattr(sink, "raise_if_cancelled", None)
    if callable(check):
        check()


def emit_progress(
    sink: Any,
    stage: str,
    message: str = "",
    *,
    current: int = 0,
    total: int = 0,
    extra: Optional[Mapping[str, Any]] = None,
) -> None:
    """Call ``sink.emit``, forwarding optional extra when the sink accepts it."""
    if sink is None:
        return
    emit = getattr(sink, "emit", None)
    if not callable(emit):
        return
    if extra is None:
        emit(stage, message, current=current, total=total)
        return
    try:
        emit(stage, message, current=current, total=total, extra=extra)
    except TypeError:
        emit(stage, message, current=current, total=total)


def emit_ops(
    sink: Any,
    message: str,
    *,
    stage: str = "log",
    current: int = 0,
    total: int = 0,
    extra: Optional[Mapping[str, Any]] = None,
) -> None:
    """Call ``sink.ops`` when the sink supports technical/debug lines."""
    if sink is None:
        return
    ops = getattr(sink, "ops", None)
    if not callable(ops):
        return
    try:
        ops(
            message,
            stage=stage,
            current=current,
            total=total,
            extra=extra,
        )
    except TypeError:
        try:
            ops(message, stage=stage, current=current, total=total)
        except TypeError:
            ops(message)


def emit_overall(
    sink: Any,
    message: str,
    *,
    stage: str = "progress",
    current: int = 0,
    total: int = 0,
    extra: Optional[Mapping[str, Any]] = None,
) -> None:
    """Call ``sink.progress`` for the sticky overall estimate (not a log line)."""
    if sink is None:
        return
    progress = getattr(sink, "progress", None)
    if not callable(progress):
        return
    try:
        progress(
            message,
            stage=stage,
            current=current,
            total=total,
            extra=extra,
        )
    except TypeError:
        try:
            progress(message, stage=stage, current=current, total=total)
        except TypeError:
            progress(message)


class OverallProgress:
    """Monotonic job-wide work units for the sticky progress strip.

    Call ``add_total`` when new work is discovered and ``tick`` when units
    complete. Totals only grow; current never resets — safe under parallel
    workers that would otherwise race per-task counters into the UI.
    """

    def __init__(
        self,
        sink: Any,
        *,
        stage: str = "progress",
        message: str = "Working…",
        interval_s: float = 0.5,
    ) -> None:
        self._sink = sink
        self._stage = stage
        self._message = message
        self._interval_s = max(0.0, float(interval_s))
        self._lock = threading.Lock()
        self._current = 0
        self._total = 0
        self._last_emit = 0.0

    def set_message(self, message: str) -> None:
        with self._lock:
            self._message = message

    def add_total(self, n: int) -> None:
        if n <= 0:
            return
        with self._lock:
            self._total += int(n)
            self._emit_unlocked(force=False)

    def tick(
        self,
        n: int = 1,
        *,
        message: Optional[str] = None,
        force: bool = False,
    ) -> None:
        if n <= 0 and not force:
            return
        with self._lock:
            if message is not None:
                self._message = message
            self._current += max(0, int(n))
            if self._current > self._total:
                self._total = self._current
            done = self._current >= self._total > 0
            self._emit_unlocked(force=force or done)

    def snapshot(self) -> tuple[int, int]:
        with self._lock:
            return self._current, self._total

    def _emit_unlocked(self, *, force: bool) -> None:
        if self._total <= 0:
            return
        now = time.monotonic()
        if not force and (now - self._last_emit) < self._interval_s:
            return
        self._last_emit = now
        current = self._current
        total = self._total
        message = self._message
        stage = self._stage
        emit_overall(
            self._sink,
            message,
            stage=stage,
            current=current,
            total=total,
        )


class ThrottledProgress:
    """Thread-safe UI progress ticks: first, last, and at most once per interval."""

    def __init__(
        self,
        sink: Any,
        *,
        stage: str,
        message: str,
        total: int,
        interval_s: float = 1.0,
    ) -> None:
        self._sink = sink
        self._stage = stage
        self._message = message
        self._total = max(0, int(total))
        self._interval_s = max(0.0, float(interval_s))
        self._lock = threading.Lock()
        self._done = 0
        self._last_emit = 0.0

    def tick(self) -> None:
        with self._lock:
            self._done += 1
            done = self._done
            total = self._total
            now = time.monotonic()
            is_edge = done == 1 or (total > 0 and done >= total)
            cooled = (now - self._last_emit) >= self._interval_s
            if not is_edge and not cooled:
                return
            self._last_emit = now
        emit_progress(
            self._sink,
            stage=self._stage,
            message=self._message,
            current=done,
            total=max(total, 1),
        )


class CancellableProgressSink:
    """Progress sink that stops the worker when ``is_cancelled`` becomes true."""

    def __init__(self, inner: ProgressSink, is_cancelled: Callable[[], bool]) -> None:
        self._inner = inner
        self._is_cancelled = is_cancelled

    def raise_if_cancelled(self) -> None:
        if self._is_cancelled():
            raise JobCancelled()

    def emit(
        self,
        stage: str,
        message: str = "",
        *,
        current: int = 0,
        total: int = 0,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.raise_if_cancelled()
        emit_progress(
            self._inner, stage, message, current=current, total=total, extra=extra
        )

    def ops(
        self,
        message: str,
        *,
        stage: str = "log",
        current: int = 0,
        total: int = 0,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.raise_if_cancelled()
        emit_ops(
            self._inner,
            message,
            stage=stage,
            current=current,
            total=total,
            extra=extra,
        )

    def progress(
        self,
        message: str,
        *,
        stage: str = "progress",
        current: int = 0,
        total: int = 0,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.raise_if_cancelled()
        emit_overall(
            self._inner,
            message,
            stage=stage,
            current=current,
            total=total,
            extra=extra,
        )


class FanOutProgressSink:
    """Call ``emit`` on each inner sink (e.g. scrape job + preview child)."""

    def __init__(self, sinks: Sequence[ProgressSink]) -> None:
        self._sinks = tuple(sinks)

    def emit(
        self,
        stage: str,
        message: str = "",
        *,
        current: int = 0,
        total: int = 0,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        for sink in self._sinks:
            emit_progress(
                sink, stage, message, current=current, total=total, extra=extra
            )

    def ops(
        self,
        message: str,
        *,
        stage: str = "log",
        current: int = 0,
        total: int = 0,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        for sink in self._sinks:
            emit_ops(
                sink,
                message,
                stage=stage,
                current=current,
                total=total,
                extra=extra,
            )

    def progress(
        self,
        message: str,
        *,
        stage: str = "progress",
        current: int = 0,
        total: int = 0,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        for sink in self._sinks:
            emit_overall(
                sink,
                message,
                stage=stage,
                current=current,
                total=total,
                extra=extra,
            )
