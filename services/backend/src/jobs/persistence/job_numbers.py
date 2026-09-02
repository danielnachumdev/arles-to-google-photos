"""Monotonic job numbers: parse, backfill, and json sequence file."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from .state import JobRecord

SEQ_FILE_NAME = "job_seq.json"
META_NEXT_KEY = "next_job_number"


def parse_job_number(raw: Any) -> Optional[int]:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value < 1:
        return None
    return value


def next_job_number(records: Sequence[JobRecord], persisted_next: int) -> int:
    max_assigned = max(
        (record.number for record in records if record.number is not None),
        default=0,
    )
    return max(max_assigned + 1, max(int(persisted_next), 1))


def assign_missing_numbers(
    records: Sequence[JobRecord],
    persisted_next: int,
) -> Tuple[List[JobRecord], int]:
    """Assign numbers to records missing one (created_at, then id). Return those updated + next."""
    current = next_job_number(records, persisted_next)
    missing = [record for record in records if record.number is None]
    missing.sort(key=lambda record: (record.created_at, record.id))
    for record in missing:
        record.number = current
        current += 1
    return missing, current


def read_seq_file(path: Path) -> int:
    if not path.is_file():
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 1
    if isinstance(data, dict):
        parsed = parse_job_number(data.get("next"))
        if parsed is not None:
            return parsed
        parsed = parse_job_number(data.get("value"))
        if parsed is not None:
            return parsed
    parsed = parse_job_number(data)
    return parsed if parsed is not None else 1


def write_seq_file(path: Path, next_value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps({"next": max(int(next_value), 1)}, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)
