"""TDD: JobEventBus fans out in-memory SSE events per job."""
from datetime import datetime, timezone
from queue import Queue

from src.jobs.events import (
    AUDIENCE_OPS,
    AUDIENCE_UI,
    KIND_LIFECYCLE,
    KIND_LOG,
    JobEvent,
    JobEventBus,
    event_from_dict,
    event_to_dict,
    filter_events_by_audience,
)
from src.progress import FanOutProgressSink, ProgressSink
from tests.support.suites import EventBusSuite






























def _next_event(subscription):
    if isinstance(subscription, Queue):
        return subscription.get_nowait()
    getter = getattr(subscription, "get_nowait", None)
    if callable(getter):
        return getter()
    getter = getattr(subscription, "get", None)
    if callable(getter):
        return getter(timeout=0)
    return next(iter(subscription))


def _queue_empty(subscription) -> bool:
    if isinstance(subscription, Queue):
        return subscription.empty()
    empty = getattr(subscription, "empty", None)
    if callable(empty):
        return empty()
    qsize = getattr(subscription, "qsize", None)
    if callable(qsize):
        return qsize() == 0
    return True

class TestJobEventBus(EventBusSuite):
    def test_emit_subscribe_receives_events_in_order(self) -> None:
        bus = JobEventBus()
        subscription = bus.subscribe("job-1")

        bus.emit("job-1", "ingest", "writing files", current=0, total=2)
        bus.emit("job-1", "parse", "hrimages/a.jpg", current=1, total=2)
        bus.emit("job-1", "preview_ready", "", current=2, total=2, extra={"items": 1})

        first = _next_event(subscription)
        second = _next_event(subscription)
        third = _next_event(subscription)

        assert [first.stage, second.stage, third.stage] == [
            "ingest",
            "parse",
            "preview_ready",
        ]
        assert first.message == "writing files"
        assert first.current == 0
        assert first.total == 2
        assert second.message == "hrimages/a.jpg"
        assert second.current == 1
        assert second.total == 2
        assert third.extra == {"items": 1}

    def test_subscribe_does_not_receive_other_jobs_events(self) -> None:
        bus = JobEventBus()
        mine = bus.subscribe("job-a")
        other = bus.subscribe("job-b")

        bus.emit("job-a", "ingest", "a only")
        bus.emit("job-b", "parse", "b only")

        assert _next_event(mine).message == "a only"
        assert _next_event(other).message == "b only"
        assert _queue_empty(mine)
        assert _queue_empty(other)

    def test_emit_sets_timezone_aware_occurred_at(self) -> None:
        bus = JobEventBus()
        before = datetime.now(timezone.utc)
        event = bus.emit("job-1", "ingest", "writing")
        after = datetime.now(timezone.utc)

        assert event.occurred_at.tzinfo is not None
        assert before <= event.occurred_at <= after

    def test_emit_calls_persist_hook(self) -> None:
        persisted = []

        def persist(job_id: str, event: JobEvent) -> None:
            persisted.append((job_id, event))

        bus = JobEventBus(persist=persist)
        event = bus.emit("job-1", "ingest", "writing", current=1, total=2)

        assert persisted == [("job-1", event)]
        assert event.stage == "ingest"
        assert event.current == 1
        assert event.total == 2

    def test_event_to_dict_includes_iso_occurred_at(self) -> None:
        occurred = datetime(2024, 6, 1, 12, 30, tzinfo=timezone.utc)
        event = JobEvent(
            job_id="job-1",
            stage="ingest",
            message="writing",
            current=1,
            total=2,
            extra={"items": 3},
            occurred_at=occurred,
        )
        payload = event_to_dict(event)
        assert payload["occurred_at"] == occurred.isoformat()
        assert payload["stage"] == "ingest"
        assert payload["kind"] == KIND_LOG
        assert payload["audience"] == AUDIENCE_UI
        restored = event_from_dict(payload)
        assert restored == event

    def test_event_from_dict_parses_zulu_and_naive(self) -> None:
        zulu = event_from_dict(
            {
                "job_id": "job-1",
                "stage": "done",
                "occurred_at": "2024-06-01T12:30:00Z",
            }
        )
        assert zulu.occurred_at.tzinfo is not None
        naive = event_from_dict(
            {"stage": "error", "occurred_at": "2024-06-01T12:30:00"},
            default_job_id="job-2",
        )
        assert naive.job_id == "job-2"
        assert naive.occurred_at.tzinfo is not None
        assert zulu.kind == KIND_LIFECYCLE
        assert naive.kind == KIND_LIFECYCLE
        assert zulu.audience == AUDIENCE_UI

    def test_fan_out_progress_sink_emits_to_all_jobs(self) -> None:
        bus = JobEventBus()
        first = bus.subscribe("job-a")
        second = bus.subscribe("job-b")
        sink: ProgressSink = FanOutProgressSink(
            (bus.sink_for("job-a"), bus.sink_for("job-b"))
        )
        sink.emit(
            "scrape",
            "Saved hrimages/a.jpg · 2/3 · 12 KB · ~1s left",
            current=2,
            total=3,
            extra={"eta_seconds": 1, "bytes_done": 24_000, "item_bytes": 12_000},
        )

        event_a = _next_event(first)
        event_b = _next_event(second)
        assert event_a.job_id == "job-a"
        assert event_b.job_id == "job-b"
        assert event_a.message == event_b.message
        assert " ~1s left" in event_a.message
        assert event_a.current == event_b.current == 2
        assert event_a.total == event_b.total == 3
        assert event_a.extra == event_b.extra == {
            "eta_seconds": 1,
            "bytes_done": 24_000,
            "item_bytes": 12_000,
        }

    def test_sink_for_matches_progress_sink_shape(self) -> None:
        bus = JobEventBus()
        subscription = bus.subscribe("job-1")
        sink = bus.sink_for("job-1")

        typed: ProgressSink = sink
        typed.emit("parse", "Parsing album export", current=0, total=4)

        event = _next_event(subscription)
        assert event.job_id == "job-1"
        assert event.stage == "parse"
        assert event.message == "Parsing album export"
        assert event.current == 0
        assert event.total == 4
        assert event.kind == KIND_LOG
        assert event.audience == AUDIENCE_UI

    def test_job_logger_ui_vs_ops_persists_kind_and_audience(self) -> None:
        persisted = []

        def persist(job_id: str, event: JobEvent) -> None:
            persisted.append((job_id, event))

        bus = JobEventBus(persist=persist)
        logger = bus.logger_for("job-1")
        ui = logger.ui(
            "Fetching gallery index",
            stage="scrape",
            current=0,
            total=16,
        )
        ops = logger.ops(
            "GET https://albums.example/index.html → 200, 812KB",
            stage="scrape",
        )

        assert ui.kind == KIND_LOG
        assert ui.audience == AUDIENCE_UI
        assert ops.kind == KIND_LOG
        assert ops.audience == AUDIENCE_OPS
        assert persisted[0][1].audience == AUDIENCE_UI
        assert persisted[1][1].audience == AUDIENCE_OPS
        assert "Authorization" not in ops.message
        assert "token" not in ops.message.lower()

    def test_progress_sink_scrape_lines_are_ui_logs(self) -> None:
        bus = JobEventBus()
        subscription = bus.subscribe("job-1")
        sink: ProgressSink = bus.sink_for("job-1")
        sink.emit("scrape", "Fetching gallery index", current=0, total=16)
        sink.emit("parse", "hrimages/a.jpg", current=1, total=16)

        first = _next_event(subscription)
        second = _next_event(subscription)
        assert first.stage == "scrape"
        assert first.kind == KIND_LOG
        assert first.audience == AUDIENCE_UI
        assert second.stage == "parse"
        assert second.kind == KIND_LOG
        assert second.audience == AUDIENCE_UI

    def test_lifecycle_emit_is_not_a_log_line(self) -> None:
        bus = JobEventBus()
        event = bus.emit(
            "job-1",
            "preview_ready",
            "Day 1",
            extra={"items": 3},
        )
        assert event.kind == KIND_LIFECYCLE
        assert event.audience == AUDIENCE_UI
        assert event.stage == "preview_ready"

    def test_old_events_without_kind_audience_still_load(self) -> None:
        scrape = event_from_dict(
            {
                "job_id": "job-1",
                "stage": "scrape",
                "message": "Fetching gallery index",
                "occurred_at": "2024-06-01T12:30:00Z",
            }
        )
        ingest = event_from_dict(
            {"job_id": "job-1", "stage": "ingest", "message": "Writing upload"}
        )
        publish = event_from_dict(
            {"job_id": "job-1", "stage": "publish", "message": "Starting upload"}
        )
        done = event_from_dict({"job_id": "job-1", "stage": "done"})
        child = event_from_dict({"job_id": "job-1", "stage": "child", "message": "preview-1"})
        assert scrape.kind == ingest.kind == publish.kind == KIND_LOG
        assert scrape.audience == AUDIENCE_UI
        assert done.kind == KIND_LIFECYCLE
        assert child.kind == KIND_LIFECYCLE
        assert done.audience == AUDIENCE_UI

    def test_filter_events_by_audience_ui_ops_all(self) -> None:
        ui = JobEvent(job_id="j", stage="scrape", message="Fetching", kind=KIND_LOG, audience=AUDIENCE_UI)
        ops = JobEvent(
            job_id="j",
            stage="scrape",
            message="GET https://example → 200, 12KB",
            kind=KIND_LOG,
            audience=AUDIENCE_OPS,
        )
        ready = JobEvent(job_id="j", stage="preview_ready", message="Day 1")
        events = [ui, ops, ready]

        default = filter_events_by_audience(events, "ui")
        assert [event.message for event in default] == ["Fetching", "Day 1"]
        assert all(event.audience != AUDIENCE_OPS or event.kind == KIND_LIFECYCLE for event in default)

        only_ops = filter_events_by_audience(events, "ops")
        assert [event.message for event in only_ops] == ["GET https://example → 200, 12KB"]

        everything = filter_events_by_audience(events, "all")
        assert everything == events

    def test_fan_out_ops_reaches_all_jobs(self) -> None:
        bus = JobEventBus()
        first = bus.subscribe("job-a")
        second = bus.subscribe("job-b")
        sink = FanOutProgressSink((bus.sink_for("job-a"), bus.sink_for("job-b")))
        sink.ops("GET https://albums.example/index.html → 200, 812KB", stage="scrape")

        event_a = _next_event(first)
        event_b = _next_event(second)
        assert event_a.audience == event_b.audience == AUDIENCE_OPS
        assert event_a.kind == event_b.kind == KIND_LOG
        assert "812KB" in event_a.message

