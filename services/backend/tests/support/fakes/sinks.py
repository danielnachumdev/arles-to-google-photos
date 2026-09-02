"""ProgressSink double that records emit/ops for assertions."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple


class RecordingSink:
    """Capture progress events. ``ops`` is optional (parser tests ignore extras)."""

    def __init__(self) -> None:
        self.events: List[Tuple[str, str, int, int]] = []
        self.extras: List[Optional[Dict[str, Any]]] = []
        self.ops_events: List[Tuple[str, str, int, int]] = []

    def emit(
        self,
        stage: str,
        message: str = "",
        *,
        current: int = 0,
        total: int = 0,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        self.events.append((stage, message, current, total))
        self.extras.append(dict(extra) if extra is not None else None)

    def ops(
        self,
        message: str,
        *,
        stage: str = "log",
        current: int = 0,
        total: int = 0,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        del extra
        self.ops_events.append((stage, message, current, total))
