"""Honest per-item scrape ETA: time per item, never assumed remaining bytes."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from ..media_kinds import VIDEO_EXTENSIONS, is_video_filename

_MIN_SAMPLES = 2
_DROP_MAX_AT = 4


@dataclass(frozen=True)
class ItemEtaSnapshot:
    """Progress after one completed media item (image page + HR download)."""

    completed: int
    total: int
    item_bytes: int
    bytes_done: int
    rate_bps: Optional[float]
    eta_seconds: Optional[float]
    is_video: bool

    def extra(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "bytes_done": self.bytes_done,
            "item_bytes": self.item_bytes,
        }
        if self.rate_bps is not None:
            payload["rate_bps"] = round(self.rate_bps, 2)
        if self.eta_seconds is not None:
            payload["eta_seconds"] = int(round(max(1.0, self.eta_seconds)))
        return payload


class ItemEtaTracker:
    """Estimate remaining time from per-item durations (median, drop one outlier)."""

    def __init__(self) -> None:
        self._durations: List[float] = []
        self._bytes_done = 0
        self._elapsed = 0.0
        self._item_started_at: Optional[float] = None

    def start_item(self, now: float) -> None:
        self._item_started_at = now

    def finish_item(
        self,
        *,
        now: float,
        item_bytes: int,
        completed: int,
        total: int,
        filename: str = "",
    ) -> ItemEtaSnapshot:
        started = self._item_started_at
        duration = max(0.0, now - started) if started is not None else 0.0
        self._item_started_at = None
        self._durations.append(duration)
        size = max(0, item_bytes)
        self._bytes_done += size
        self._elapsed += duration
        remaining = max(0, total - completed)
        typical = _typical_seconds(self._durations)
        eta: Optional[float] = None
        if (
            len(self._durations) >= _MIN_SAMPLES
            and remaining > 0
            and typical is not None
        ):
            eta = remaining * typical
        rate: Optional[float] = None
        if self._elapsed > 0 and self._bytes_done > 0:
            rate = self._bytes_done / self._elapsed
        return ItemEtaSnapshot(
            completed=completed,
            total=total,
            item_bytes=size,
            bytes_done=self._bytes_done,
            rate_bps=rate,
            eta_seconds=eta,
            is_video=is_video_filename(filename),
        )


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    kb = size / 1024.0
    if kb < 1024:
        return _pretty_unit(kb, "KB", max_decimals=1 if kb < 10 else 0)
    mb = kb / 1024.0
    if mb < 1024:
        return _pretty_unit(mb, "MB", max_decimals=1)
    return _pretty_unit(mb / 1024.0, "GB", max_decimals=1)


def format_eta(seconds: float) -> str:
    total = int(round(max(0.0, seconds)))
    if total < 1:
        total = 1
    if total < 60:
        return f"~{total}s left"
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        if minutes:
            return f"~{hours}h {minutes}m left"
        return f"~{hours}h left"
    if secs:
        return f"~{minutes}m {secs}s left"
    return f"~{minutes}m left"


def saved_hr_message(hr_name: str, snapshot: ItemEtaSnapshot) -> str:
    size = format_bytes(snapshot.item_bytes)
    size_part = f"video {size}" if snapshot.is_video else size
    parts = [
        f"Saved hrimages/{hr_name}",
        f"{snapshot.completed}/{snapshot.total}",
        size_part,
    ]
    if snapshot.eta_seconds is not None:
        parts.append(format_eta(snapshot.eta_seconds))
    return " · ".join(parts)


def _typical_seconds(durations: Sequence[float]) -> Optional[float]:
    if not durations:
        return None
    samples = list(durations)
    if len(samples) >= _DROP_MAX_AT:
        samples.remove(max(samples))
    return float(statistics.median(samples))


def _pretty_unit(value: float, unit: str, *, max_decimals: int) -> str:
    if max_decimals <= 0 or abs(value - round(value)) < 0.05:
        return f"{int(round(value))} {unit}"
    return f"{value:.{max_decimals}f} {unit}"
