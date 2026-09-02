"""In-memory per-job event fan-out for SSE (no Redis)."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Queue
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

PersistHook = Callable[[str, "JobEvent"], Any]

KIND_LOG = "log"
KIND_LIFECYCLE = "lifecycle"
AUDIENCE_UI = "ui"
AUDIENCE_OPS = "ops"

LIFECYCLE_STAGES = frozenset(
    {"done", "error", "failed", "cancelled", "preview_ready", "child", "waiting"}
)
_KIND_ALIASES = {"progress": KIND_LIFECYCLE}


def _parse_occurred_at(raw: Optional[Any]) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    occurred_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    return occurred_at


def infer_event_kind(stage: str, kind: Optional[str] = None) -> str:
    if kind:
        normalized = str(kind).strip().lower()
        if normalized in _KIND_ALIASES:
            return _KIND_ALIASES[normalized]
        if normalized in {KIND_LOG, KIND_LIFECYCLE}:
            return normalized
    if str(stage or "") in LIFECYCLE_STAGES:
        return KIND_LIFECYCLE
    return KIND_LOG


def infer_event_audience(audience: Optional[str] = None) -> str:
    if audience and str(audience).strip().lower() == AUDIENCE_OPS:
        return AUDIENCE_OPS
    return AUDIENCE_UI


def filter_events_by_audience(
    events: Sequence["JobEvent"],
    audience: str = AUDIENCE_UI,
) -> List["JobEvent"]:
    wanted = str(audience or AUDIENCE_UI).strip().lower()
    if wanted == "all":
        return list(events)
    if wanted == AUDIENCE_OPS:
        return [event for event in events if event.audience == AUDIENCE_OPS]
    return [
        event
        for event in events
        if event.kind == KIND_LIFECYCLE or event.audience != AUDIENCE_OPS
    ]


@dataclass(frozen=True)
class JobEvent:
    job_id: str
    stage: str
    message: str = ""
    current: int = 0
    total: int = 0
    extra: Optional[Dict[str, Any]] = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    kind: str = ""
    audience: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "kind", infer_event_kind(self.stage, self.kind or None)
        )
        object.__setattr__(
            self, "audience", infer_event_audience(self.audience or None)
        )


def event_to_dict(event: JobEvent) -> Dict[str, Any]:
    return {
        "job_id": event.job_id,
        "stage": event.stage,
        "message": event.message,
        "current": event.current,
        "total": event.total,
        "extra": event.extra,
        "occurred_at": event.occurred_at.isoformat(),
        "kind": event.kind,
        "audience": event.audience,
    }


def event_from_dict(
    data: Mapping[str, Any],
    *,
    default_job_id: str = "",
) -> JobEvent:
    extra = data.get("extra")
    extra_dict = extra if isinstance(extra, dict) else None
    stage = str(data.get("stage") or "")
    kind_raw = data.get("kind")
    audience_raw = data.get("audience")
    return JobEvent(
        job_id=str(data.get("job_id") or default_job_id),
        stage=stage,
        message=str(data.get("message") or ""),
        current=int(data.get("current") or 0),
        total=int(data.get("total") or 0),
        extra=extra_dict,
        occurred_at=_parse_occurred_at(data.get("occurred_at")),
        kind=infer_event_kind(stage, str(kind_raw) if kind_raw else None),
        audience=infer_event_audience(str(audience_raw) if audience_raw else None),
    )


@dataclass
class JobLogger:
    """Per-job logger: UI lines, ops/debug lines, and ``ProgressSink.emit``."""

    bus: "JobEventBus"
    job_id: str

    def ui(
        self,
        message: str,
        *,
        stage: str = "log",
        current: int = 0,
        total: int = 0,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> JobEvent:
        return self.bus.emit(
            self.job_id,
            stage,
            message,
            current=current,
            total=total,
            extra=dict(extra) if extra is not None else None,
            kind=KIND_LOG,
            audience=AUDIENCE_UI,
        )

    def ops(
        self,
        message: str,
        *,
        stage: str = "log",
        current: int = 0,
        total: int = 0,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> JobEvent:
        return self.bus.emit(
            self.job_id,
            stage,
            message,
            current=current,
            total=total,
            extra=dict(extra) if extra is not None else None,
            kind=KIND_LOG,
            audience=AUDIENCE_OPS,
        )

    def emit(
        self,
        stage: str,
        message: str = "",
        *,
        current: int = 0,
        total: int = 0,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """``ProgressSink``: user-facing log line (not a lifecycle stage)."""
        self.ui(
            message,
            stage=stage,
            current=current,
            total=total,
            extra=extra,
        )


JobProgressSink = JobLogger


@dataclass
class JobEventBus:
    """Per-job queues of ``JobEvent`` for SSE subscribers."""

    persist: Optional[PersistHook] = None
    _history: Dict[str, List[JobEvent]] = field(default_factory=dict)
    _subscribers: Dict[str, List[Queue[JobEvent]]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def emit(
        self,
        job_id: str,
        stage: str,
        message: str = "",
        *,
        current: int = 0,
        total: int = 0,
        extra: Optional[Dict[str, Any]] = None,
        kind: Optional[str] = None,
        audience: Optional[str] = None,
    ) -> JobEvent:
        event = JobEvent(
            job_id=job_id,
            stage=stage,
            message=message,
            current=current,
            total=total,
            extra=extra,
            kind=infer_event_kind(stage, kind),
            audience=infer_event_audience(audience),
        )
        with self._lock:
            self._history.setdefault(job_id, []).append(event)
            subscribers = list(self._subscribers.get(job_id, ()))
        for queue in subscribers:
            queue.put(event)
        if self.persist is not None:
            try:
                self.persist(job_id, event)
            except KeyError:
                pass
        return event

    def subscribe(self, job_id: str) -> Queue[JobEvent]:
        queue: Queue[JobEvent] = Queue()
        with self._lock:
            history = list(self._history.get(job_id, ()))
            self._subscribers.setdefault(job_id, []).append(queue)
        for event in history:
            queue.put(event)
        return queue

    def sink_for(self, job_id: str) -> JobLogger:
        return JobLogger(self, job_id)

    def logger_for(self, job_id: str) -> JobLogger:
        return JobLogger(self, job_id)
