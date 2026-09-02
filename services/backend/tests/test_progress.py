"""Progress sink helpers: emit fallbacks, fan-out, cancellation."""
from __future__ import annotations

import pytest

from src.progress import (
    CancellableProgressSink,
    FanOutProgressSink,
    JobCancelled,
    emit_ops,
    emit_progress,
    raise_if_cancelled,
)
from tests.support.fakes.sinks import RecordingSink
from tests.support.suites import ProgressSuite


class TestProgressHelpers(ProgressSuite):
    def test_emit_progress_noop_without_sink_or_emit(self) -> None:
        emit_progress(None, "stage")
        emit_progress(object(), "stage", extra={"a": 1})

    def test_emit_progress_drops_extra_on_typeerror(self) -> None:
        class Sink:
            def __init__(self) -> None:
                self.calls: list[tuple] = []

            def emit(self, stage: str, message: str = "", *, current: int = 0, total: int = 0):
                self.calls.append((stage, message, current, total))

        sink = Sink()
        emit_progress(sink, "ingest", "hi", extra={"items": 1})
        assert sink.calls == [("ingest", "hi", 0, 0)]

    def test_emit_ops_fallbacks(self) -> None:
        emit_ops(None, "hello")
        emit_ops(object(), "hello")

        class MessageOnly:
            def __init__(self) -> None:
                self.msg = ""

            def ops(self, message: str) -> None:
                self.msg = message

        message_only = MessageOnly()
        emit_ops(message_only, "hello", extra={"x": 1})
        assert message_only.msg == "hello"

        class NoExtra:
            def __init__(self) -> None:
                self.stage = ""

            def ops(self, message: str, *, stage: str = "log", current: int = 0, total: int = 0):
                del message, current, total
                self.stage = stage

        no_extra = NoExtra()
        emit_ops(no_extra, "hello", extra={"x": 1})
        assert no_extra.stage == "log"

    def test_raise_if_cancelled_ignores_plain_sink(self) -> None:
        raise_if_cancelled(None)
        raise_if_cancelled(object())

    def test_cancellable_sink_stops_emit_and_ops(self) -> None:
        inner = self.sink
        cancelled = {"flag": False}
        sink = CancellableProgressSink(inner, lambda: cancelled["flag"])
        sink.emit("ingest", "ok")
        sink.ops("log line")
        cancelled["flag"] = True
        with pytest.raises(JobCancelled):
            sink.emit("ingest", "nope")
        with pytest.raises(JobCancelled):
            sink.ops("nope")
        assert inner.events[0][0] == "ingest"
        assert inner.ops_events[0][1] == "log line"

    def test_fanout_progress_sink_forwards_emit_and_ops(self) -> None:
        first = RecordingSink()
        second = RecordingSink()
        fan = FanOutProgressSink((first, second))
        fan.emit("parse", "a.jpg", current=1, total=2, extra={"n": 1})
        fan.ops("GET /index.html", stage="scrape")
        assert first.events == second.events == [("parse", "a.jpg", 1, 2)]
        assert first.ops_events == second.ops_events == [("scrape", "GET /index.html", 0, 0)]
