"""Filesystem StateStore: ``{job_id}/job.json`` + ``events.json``."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..events import JobEvent, event_from_dict, event_to_dict
from ..store import (
    EVENTS_NAME,
    JOB_META_NAME,
    JobNotFoundError,
    normalize_job_state,
    parse_created_at,
    parse_error_code,
    parse_extra,
    parse_optional_datetime,
    parse_run_seconds,
    parse_user_edited,
    parse_warnings,
    preview_from_dict,
    preview_to_dict,
)
from .job_numbers import (
    SEQ_FILE_NAME,
    assign_missing_numbers,
    parse_job_number,
    read_seq_file,
    write_seq_file,
)

META_FILE_NAME = "meta.json"
from .paths import validate_job_id
from .state import JobRecord, StateStore, infer_import_origin


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON via a unique temp file so concurrent savers cannot share ``.tmp``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Include xdist worker + pid + random suffix: fixed ``job.json.tmp`` races when
    # orchestrator and cancel both save the same job (and under ``pytest -n``).
    worker = os.environ.get("PYTEST_XDIST_WORKER") or "main"
    tmp = path.with_name(
        f"{path.name}.{worker}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # Windows can deny replace while another thread still has ``path`` open.
        last_err: Optional[PermissionError] = None
        for attempt in range(40):
            try:
                tmp.replace(path)
                last_err = None
                break
            except PermissionError as exc:
                last_err = exc
                time.sleep(0.01 * (1 + attempt // 10))
        if last_err is not None:
            raise last_err
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def record_from_meta(data: Dict[str, Any], *, fallback_id: str = "") -> JobRecord:
    job_id = str(data.get("id") or fallback_id)
    if not job_id:
        raise ValueError("missing job id")
    product_url = data.get("product_url")
    status, job_type = normalize_job_state(
        data.get("status"),
        data.get("type"),
        product_url,
    )
    source_raw = data.get("source_job_id")
    source_job_id = str(source_raw) if source_raw else None
    parent_raw = data.get("parent_job_id")
    parent_job_id = str(parent_raw) if parent_raw else None
    scrape_url_raw = data.get("scrape_url")
    scrape_url = str(scrape_url_raw) if scrape_url_raw else None
    scrape_headers = _headers_from_meta(data.get("scrape_headers"))
    number = parse_job_number(data.get("number"))
    if number is None:
        number = parse_job_number(data.get("job_number"))
    import_origin = infer_import_origin(
        import_origin=data.get("import_origin"),
        job_type=job_type,
        parent_job_id=parent_job_id,
        scrape_url=scrape_url,
    )
    return JobRecord(
        id=job_id,
        status=status,
        type=job_type,
        preview=preview_from_dict(data.get("preview")),
        error=data.get("error"),
        error_code=parse_error_code(data.get("error_code")),
        product_url=product_url,
        created_at=parse_created_at(data.get("created_at")),
        started_at=parse_optional_datetime(data.get("started_at")),
        running_started_at=parse_optional_datetime(data.get("running_started_at")),
        run_seconds=parse_run_seconds(data.get("run_seconds")),
        folder_label=data.get("folder_label"),
        source_job_id=source_job_id,
        parent_job_id=parent_job_id,
        scrape_url=scrape_url,
        scrape_headers=scrape_headers,
        number=number,
        auto_publish=bool(data.get("auto_publish")),
        warnings=parse_warnings(data.get("warnings")),
        import_origin=import_origin,
        user_edited=parse_user_edited(data.get("user_edited")),
        archived_at=parse_optional_datetime(data.get("archived_at")),
        extra=parse_extra(data.get("extra")),
        owner_id=str(data["owner_id"]) if data.get("owner_id") else None,
    )


def record_to_meta(record: JobRecord) -> Dict[str, Any]:
    return {
        "id": record.id,
        "status": record.status,
        "type": record.type,
        "error": record.error,
        "error_code": record.error_code,
        "preview": preview_to_dict(record.preview),
        "product_url": record.product_url,
        "created_at": record.created_at.isoformat(),
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "running_started_at": (
            record.running_started_at.isoformat() if record.running_started_at else None
        ),
        "run_seconds": record.run_seconds,
        "folder_label": record.folder_label,
        "source_job_id": record.source_job_id,
        "parent_job_id": record.parent_job_id,
        "scrape_url": record.scrape_url,
        "scrape_headers": record.scrape_headers,
        "number": record.number,
        "auto_publish": bool(record.auto_publish),
        "warnings": list(record.warnings or []),
        "import_origin": record.resolved_import_origin(),
        "user_edited": bool(record.user_edited),
        "archived_at": record.archived_at.isoformat() if record.archived_at else None,
        "extra": parse_extra(record.extra),
        "owner_id": record.owner_id,
    }


def _headers_from_meta(raw: Any) -> Optional[Dict[str, str]]:
    if not isinstance(raw, dict) or not raw:
        return None
    return {str(key): str(value) for key, value in raw.items()}


def load_events_file(path: Path, job_id: str) -> List[JobEvent]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []
    if isinstance(data, dict):
        raw_events = data.get("events") or []
    elif isinstance(data, list):
        raw_events = data
    else:
        return []
    loaded: List[JobEvent] = []
    for raw in raw_events:
        if isinstance(raw, dict):
            loaded.append(event_from_dict(raw, default_job_id=job_id))
    return loaded


def _read_meta_file(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


class JsonStateStore(StateStore):
    """Write-through ``job.json`` / ``events.json`` under ``{base_dir}/{job_id}/``."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._seq_lock = threading.Lock()
        self._backfill_numbers()

    def allocate_number(self) -> int:
        with self._seq_lock:
            return self._allocate_unlocked()

    def create(self, record: JobRecord) -> JobRecord:
        if record.number is None:
            record.number = self.allocate_number()
        job_dir = self._job_dir(record.id)
        job_dir.mkdir(parents=True, exist_ok=True)
        meta_path = job_dir / JOB_META_NAME
        if meta_path.is_file():
            raise ValueError(f"job already exists: {record.id}")
        _atomic_write_json(meta_path, record_to_meta(record))
        return record

    def get(self, job_id: str, *, owner_id: Optional[str] = None) -> JobRecord:
        data = _read_meta_file(self._job_dir(job_id) / JOB_META_NAME)
        if data is None:
            raise JobNotFoundError(job_id)
        try:
            record = record_from_meta(data, fallback_id=job_id)
        except (TypeError, ValueError, KeyError) as exc:
            raise JobNotFoundError(job_id) from exc
        if (
            owner_id is not None
            and record.owner_id is not None
            and record.owner_id != owner_id
        ):
            raise JobNotFoundError(job_id)
        return record

    def list_all(self, *, owner_id: Optional[str] = None) -> List[JobRecord]:
        if not self._base_dir.is_dir():
            return []
        records: List[JobRecord] = []
        for child in self._base_dir.iterdir():
            if not child.is_dir():
                continue
            data = _read_meta_file(child / JOB_META_NAME)
            if data is None:
                continue
            try:
                record = record_from_meta(data, fallback_id=child.name)
            except (TypeError, ValueError, KeyError):
                continue
            if (
                owner_id is not None
                and record.owner_id is not None
                and record.owner_id != owner_id
            ):
                continue
            records.append(record)
        return records

    def save(self, record: JobRecord) -> JobRecord:
        job_dir = self._job_dir(record.id)
        meta_path = job_dir / JOB_META_NAME
        if not meta_path.is_file():
            raise JobNotFoundError(record.id)
        if record.number is None:
            existing = _read_meta_file(meta_path)
            if existing is not None:
                record.number = parse_job_number(existing.get("number"))
                if record.number is None:
                    record.number = parse_job_number(existing.get("job_number"))
        _atomic_write_json(meta_path, record_to_meta(record))
        return record

    def delete(self, job_id: str) -> None:
        job_dir = self._job_dir(job_id)
        meta_path = job_dir / JOB_META_NAME
        if not meta_path.is_file():
            raise JobNotFoundError(job_id)
        for name in (
            JOB_META_NAME,
            EVENTS_NAME,
            f"{JOB_META_NAME}.tmp",
            f"{EVENTS_NAME}.tmp",
        ):
            path = job_dir / name
            if path.is_file():
                path.unlink()

    def append_event(self, job_id: str, event: JobEvent) -> None:
        job_dir = self._job_dir(job_id)
        if not (job_dir / JOB_META_NAME).is_file():
            raise JobNotFoundError(job_id)
        events = load_events_file(job_dir / EVENTS_NAME, job_id)
        events.append(event)
        _atomic_write_json(
            job_dir / EVENTS_NAME,
            {"events": [event_to_dict(item) for item in events]},
        )

    def list_events(self, job_id: str) -> List[JobEvent]:
        job_dir = self._job_dir(job_id)
        if not (job_dir / JOB_META_NAME).is_file():
            raise JobNotFoundError(job_id)
        return load_events_file(job_dir / EVENTS_NAME, job_id)

    def get_meta(self, key: str) -> Optional[str]:
        data = _read_meta_file(self._meta_path())
        if not isinstance(data, dict):
            return None
        if key not in data:
            return None
        value = data.get(key)
        if value is None:
            return None
        return str(value)

    def set_meta(self, key: str, value: str) -> None:
        data = _read_meta_file(self._meta_path())
        payload: Dict[str, Any] = dict(data) if isinstance(data, dict) else {}
        payload[str(key)] = str(value)
        _atomic_write_json(self._meta_path(), payload)

    def _meta_path(self) -> Path:
        return self._base_dir / META_FILE_NAME

    def _job_dir(self, job_id: str) -> Path:
        return self._base_dir / validate_job_id(job_id)

    def _seq_path(self) -> Path:
        return self._base_dir / SEQ_FILE_NAME

    def _allocate_unlocked(self) -> int:
        next_value = read_seq_file(self._seq_path())
        write_seq_file(self._seq_path(), next_value + 1)
        return next_value

    def _backfill_numbers(self) -> None:
        records = self.list_all()
        with self._seq_lock:
            persisted = read_seq_file(self._seq_path())
            assigned, next_value = assign_missing_numbers(records, persisted)
            for record in assigned:
                meta_path = self._job_dir(record.id) / JOB_META_NAME
                if meta_path.is_file():
                    _atomic_write_json(meta_path, record_to_meta(record))
            write_seq_file(self._seq_path(), next_value)
