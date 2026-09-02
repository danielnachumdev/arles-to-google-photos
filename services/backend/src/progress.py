"""Progress reporting shared by parser, publisher, scrape, and SSE."""
from __future__ import annotations

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
