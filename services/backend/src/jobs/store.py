"""Job facade: in-memory cache over StateStore + ArtifactStore."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from ..export.media_kinds import infer_item_kind
from ..export.preview import AlbumJournal, AlbumPreview, PreviewItem
from .events import JobEvent
from .persistence.artifacts import ArtifactStore
from .persistence.state import (
    ORIGIN_FOLDER,
    JobRecord,
    StateStore,
    infer_import_origin,
)

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_WAITING = "waiting"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
TYPE_PREVIEW = "preview"
TYPE_UPLOAD = "upload"
TYPE_SCRAPE = "scrape"
_TERMINAL_STATUSES = frozenset({STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED})
_ACTIVE_STATUSES = frozenset({STATUS_PENDING, STATUS_RUNNING, STATUS_WAITING})
_VALID_STATUSES = frozenset(
    {
        STATUS_PENDING,
        STATUS_RUNNING,
        STATUS_WAITING,
        STATUS_DONE,
        STATUS_FAILED,
        STATUS_CANCELLED,
    }
)
_VALID_TYPES = frozenset({TYPE_PREVIEW, TYPE_UPLOAD, TYPE_SCRAPE})
_LEGACY_STATUS_MAP = {
    "created": (STATUS_PENDING, TYPE_PREVIEW),
    "ingesting": (STATUS_RUNNING, TYPE_PREVIEW),
    "preview_ready": (STATUS_DONE, TYPE_PREVIEW),
    "publishing": (STATUS_RUNNING, TYPE_UPLOAD),
}

JOB_META_NAME = "job.json"
EVENTS_NAME = "events.json"


class JobNotFoundError(KeyError):
    """Raised when a job id is not present in the store."""


class JobNotCancellableError(ValueError):
    """Raised when cancel is requested for a job that is already terminal."""


class JobNotArchivableError(ValueError):
    """Raised when archive is requested for a non-terminal job or tree."""


@dataclass
class Job:
    id: str
    root: Path
    status: str = STATUS_PENDING
    type: str = TYPE_PREVIEW
    preview: Optional[AlbumPreview] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    product_url: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    running_started_at: Optional[datetime] = None
    run_seconds: Optional[float] = None
    folder_label: Optional[str] = None
    source_job_id: Optional[str] = None
    parent_job_id: Optional[str] = None
    scrape_url: Optional[str] = None
    scrape_headers: Optional[Dict[str, str]] = None
    number: Optional[int] = None
    auto_publish: bool = False
    warnings: List[str] = field(default_factory=list)
    import_origin: str = ORIGIN_FOLDER
    user_edited: bool = False
    archived_at: Optional[datetime] = None
    extra: Optional[Dict[str, Any]] = None
    owner_id: Optional[str] = None
    events: List[JobEvent] = field(default_factory=list)


def _isoformat(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def preview_to_dict(preview: Optional[AlbumPreview]) -> Optional[Dict[str, Any]]:
    if preview is None:
        return None
    journal = None
    if preview.journal is not None:
        journal = {
            "heading": preview.journal.heading,
            "paragraphs": list(preview.journal.paragraphs),
        }
    return {
        "title": preview.title,
        "description": preview.description,
        "multi_index": preview.multi_index,
        "structure_fallback": bool(preview.structure_fallback),
        "journal": journal,
        "items": [
            {
                "id": item.id,
                "relpath": item.relpath,
                "caption": item.caption,
                "size_bytes": item.size_bytes,
                "last_modified": _isoformat(item.last_modified),
                "taken_on": item.taken_on.isoformat() if item.taken_on else None,
                "kind": infer_item_kind(item.relpath, item.kind),
                "thumb_relpath": item.thumb_relpath,
                "play_relpath": item.play_relpath,
            }
            for item in preview.items
        ],
    }


def preview_from_dict(data: Optional[Any]) -> Optional[AlbumPreview]:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError("preview must be an object")
    journal_data = data.get("journal")
    journal = None
    if journal_data is not None:
        if not isinstance(journal_data, dict):
            raise ValueError("journal must be an object")
        paragraphs = journal_data.get("paragraphs") or []
        journal = AlbumJournal(
            heading=journal_data.get("heading"),
            paragraphs=tuple(str(part) for part in paragraphs),
        )
    items = []
    for raw in data.get("items") or []:
        if not isinstance(raw, dict):
            raise ValueError("preview item must be an object")
        last_modified = None
        if raw.get("last_modified"):
            last_modified = datetime.fromisoformat(str(raw["last_modified"]))
        taken_on = None
        if raw.get("taken_on"):
            taken_on = date.fromisoformat(str(raw["taken_on"]))
        relpath = str(raw["relpath"])
        thumb_raw = raw.get("thumb_relpath")
        play_raw = raw.get("play_relpath")
        items.append(
            PreviewItem(
                id=str(raw["id"]),
                relpath=relpath,
                caption=str(raw.get("caption") or ""),
                size_bytes=int(raw.get("size_bytes") or 0),
                last_modified=last_modified,
                taken_on=taken_on,
                kind=infer_item_kind(relpath, raw.get("kind")),
                thumb_relpath=str(thumb_raw) if thumb_raw else None,
                play_relpath=str(play_raw) if play_raw else None,
            )
        )
    return AlbumPreview(
        title=str(data.get("title") or ""),
        description=data.get("description"),
        multi_index=bool(data.get("multi_index")),
        items=tuple(items),
        journal=journal,
        structure_fallback=bool(data.get("structure_fallback")),
    )


def normalize_job_state(
    status: Optional[str],
    job_type: Optional[str] = None,
    product_url: Optional[str] = None,
) -> Tuple[str, str]:
    """Map legacy or missing status/type onto pending|running|waiting|done|failed|cancelled and preview|upload|scrape."""
    raw_status = str(status or "").strip().lower() or None
    raw_type = str(job_type or "").strip().lower() or None
    valid_type = raw_type if raw_type in _VALID_TYPES else None
    inferred_type = TYPE_UPLOAD if product_url else TYPE_PREVIEW

    if raw_status in _LEGACY_STATUS_MAP:
        new_status, mapped_type = _LEGACY_STATUS_MAP[raw_status]
        return new_status, valid_type or mapped_type
    if raw_status == "error":
        return STATUS_FAILED, valid_type or inferred_type
    if raw_status == STATUS_DONE:
        return STATUS_DONE, valid_type or inferred_type
    if raw_status in _VALID_STATUSES:
        return raw_status, valid_type or inferred_type
    return STATUS_PENDING, valid_type or inferred_type


def parse_warnings(raw: Optional[Any]) -> List[str]:
    if not isinstance(raw, list):
        return []
    warnings: List[str] = []
    for item in raw:
        text = str(item).strip()
        if text:
            warnings.append(text)
    return warnings


def parse_extra(raw: Optional[Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict) or not raw:
        return None
    return dict(raw)


def parse_error_code(raw: Optional[Any]) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def parse_user_edited(raw: Optional[Any]) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes"}
    return False


def parse_created_at(raw: Optional[Any]) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    created_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at


def parse_optional_datetime(raw: Optional[Any]) -> Optional[datetime]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return parse_created_at(text)


def parse_run_seconds(raw: Optional[Any]) -> Optional[float]:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value < 0.0 or value != value:
        return None
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _apply_run_timing(job: Job, new_status: str, *, now: Optional[datetime] = None) -> None:
    """Accumulate time spent in ``running``; pending and waiting do not count."""
    clock = now if now is not None else _utc_now()
    old_status = job.status
    if old_status == new_status:
        return
    if old_status == STATUS_RUNNING and job.running_started_at is not None:
        elapsed = (clock - job.running_started_at).total_seconds()
        job.run_seconds = (job.run_seconds or 0.0) + max(0.0, elapsed)
        job.running_started_at = None
    if new_status == STATUS_RUNNING:
        if job.run_seconds is None:
            job.run_seconds = 0.0
        job.running_started_at = clock
        if job.started_at is None:
            job.started_at = clock
        return
    job.running_started_at = None
    if new_status in _TERMINAL_STATUSES or new_status == STATUS_WAITING:
        if job.run_seconds is None:
            job.run_seconds = 0.0


def _run_duration_seconds(job: Job, *, now: Optional[datetime] = None) -> Optional[int]:
    tracked = (
        job.run_seconds is not None
        or job.running_started_at is not None
        or job.started_at is not None
    )
    if not tracked:
        return None
    elapsed = float(job.run_seconds or 0.0)
    if job.status == STATUS_RUNNING and job.running_started_at is not None:
        clock = now if now is not None else _utc_now()
        elapsed += max(0.0, (clock - job.running_started_at).total_seconds())
    return max(0, int(elapsed))


def job_from_meta(data: Dict[str, Any], root: Path) -> Job:
    job_id = str(data.get("id") or root.name)
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
    headers_raw = data.get("scrape_headers")
    scrape_headers = None
    if isinstance(headers_raw, dict) and headers_raw:
        scrape_headers = {str(key): str(value) for key, value in headers_raw.items()}
    number_raw = data.get("number")
    if number_raw is None:
        number_raw = data.get("job_number")
    number: Optional[int] = None
    if number_raw is not None and not isinstance(number_raw, bool):
        try:
            parsed = int(number_raw)
        except (TypeError, ValueError):
            parsed = 0
        if parsed >= 1:
            number = parsed
    import_origin = infer_import_origin(
        import_origin=data.get("import_origin"),
        job_type=job_type,
        parent_job_id=parent_job_id,
        scrape_url=scrape_url,
    )
    return Job(
        id=job_id,
        root=root,
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
    )


def job_to_dict(
    job: Job,
    *,
    child_ids: Optional[List[str]] = None,
    preview_job_id: Optional[str] = None,
) -> Dict[str, Any]:
    header_names = list((job.scrape_headers or {}).keys())
    updated_at, finished_at, duration_seconds, last_stage = _summary_timing(job)
    return {
        "id": job.id,
        "number": job.number,
        "status": job.status,
        "type": job.type,
        "error": job.error,
        "error_code": job.error_code,
        "warnings": list(job.warnings or []),
        "preview": preview_to_dict(job.preview),
        "product_url": job.product_url,
        "created_at": job.created_at.isoformat(),
        "started_at": _isoformat(job.started_at),
        "running_started_at": _isoformat(job.running_started_at),
        "updated_at": updated_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "last_stage": last_stage,
        "archived_at": _isoformat(job.archived_at),
        "folder_label": job.folder_label,
        "source_job_id": job.source_job_id,
        "parent_job_id": job.parent_job_id,
        "scrape_url": job.scrape_url,
        "has_headers": bool(job.scrape_headers),
        "header_names": header_names,
        "child_ids": list(child_ids or ()),
        "preview_job_id": preview_job_id,
        "auto_publish": bool(job.auto_publish),
        "user_edited": bool(job.user_edited),
        "import_origin": infer_import_origin(
            import_origin=job.import_origin,
            job_type=job.type,
            parent_job_id=job.parent_job_id,
            scrape_url=job.scrape_url,
        ),
    }


def album_identity_key(title: Optional[str]) -> Optional[str]:
    """Normalized album identity: trimmed preview title, or None if empty."""
    if title is None:
        return None
    stripped = str(title).strip()
    return stripped or None


def job_album_key(job: Job) -> Optional[str]:
    if job.preview is not None:
        key = album_identity_key(job.preview.title)
        if key is not None:
            return key
    if job.scrape_url:
        return album_identity_key(job.scrape_url)
    return None


def job_display_title(job: Job) -> Optional[str]:
    if job.type == TYPE_SCRAPE:
        return None
    if job.preview is not None:
        stripped = str(job.preview.title or "").strip()
        if stripped:
            return stripped
    return None


def _is_library_album(job: Job) -> bool:
    """True when the job can be opened on the album desk (saved preview)."""
    if job.type == TYPE_SCRAPE:
        return False
    if job.preview is None:
        return False
    return album_identity_key(job.preview.title) is not None


def _pick_album_winner(jobs: List[Job]) -> Job:
    def sort_key(job: Job) -> Tuple[int, int, datetime, str]:
        is_preview = 1 if job.type == TYPE_PREVIEW else 0
        has_url = 1 if job.product_url else 0
        return (is_preview, has_url, job.created_at, job.id)

    return max(jobs, key=sort_key)


def _summary_timing(
    job: Job,
) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[str]]:
    last_event = job.events[-1] if job.events else None
    updated_at = last_event.occurred_at if last_event is not None else job.created_at
    last_stage = last_event.stage if last_event is not None else None
    duration_seconds = _run_duration_seconds(job)
    if job.status in _TERMINAL_STATUSES:
        if duration_seconds is None:
            duration_seconds = max(
                0, int((updated_at - job.created_at).total_seconds())
            )
        return (
            _isoformat(updated_at),
            _isoformat(updated_at),
            duration_seconds,
            last_stage,
        )
    return (_isoformat(updated_at), None, duration_seconds, last_stage)


def _first_preview_child_ids(jobs: List[Job]) -> Dict[str, str]:
    grouped: Dict[str, List[Job]] = {}
    for job in jobs:
        if job.parent_job_id and job.type == TYPE_PREVIEW:
            grouped.setdefault(job.parent_job_id, []).append(job)
    result: Dict[str, str] = {}
    for parent_id, children in grouped.items():
        children.sort(key=lambda child: (child.created_at, child.id))
        result[parent_id] = children[0].id
    return result


def job_summary_to_dict(
    job: Job,
    *,
    preview_job_id: Optional[str] = None,
) -> Dict[str, Any]:
    preview = job.preview
    updated_at, finished_at, duration_seconds, last_stage = _summary_timing(job)
    return {
        "id": job.id,
        "number": job.number,
        "status": job.status,
        "type": job.type,
        "error": job.error,
        "error_code": job.error_code,
        "warnings": list(job.warnings or []),
        "title": job_display_title(job),
        "item_count": len(preview.items) if preview is not None else 0,
        "created_at": job.created_at.isoformat(),
        "started_at": _isoformat(job.started_at),
        "running_started_at": _isoformat(job.running_started_at),
        "product_url": job.product_url,
        "folder_label": job.folder_label,
        "updated_at": updated_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "last_stage": last_stage,
        "archived_at": _isoformat(job.archived_at),
        "source_job_id": job.source_job_id,
        "parent_job_id": job.parent_job_id,
        "scrape_url": job.scrape_url,
        "preview_job_id": preview_job_id,
        "auto_publish": bool(job.auto_publish),
        "user_edited": bool(job.user_edited),
        "import_origin": infer_import_origin(
            import_origin=job.import_origin,
            job_type=job.type,
            parent_job_id=job.parent_job_id,
            scrape_url=job.scrape_url,
        ),
    }


def summarize_jobs(
    jobs: List[Job],
    *,
    all_jobs: Optional[List[Job]] = None,
) -> List[Dict[str, Any]]:
    preview_ids = _first_preview_child_ids(
        all_jobs if all_jobs is not None else jobs
    )
    return [
        job_summary_to_dict(job, preview_job_id=preview_ids.get(job.id))
        for job in jobs
    ]


@dataclass
class JobStore:
    """Create/get/update/delete jobs. Domain facade over state + artifact stores."""

    base_dir: Optional[Path] = None
    _state: Optional[StateStore] = None
    _artifacts: Optional[ArtifactStore] = None
    _jobs: Dict[str, Job] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _cancel_requested: Set[str] = field(default_factory=set)

    @classmethod
    def load(
        cls,
        base_dir: Path,
        *,
        state: Optional[StateStore] = None,
        artifacts: Optional[ArtifactStore] = None,
    ) -> "JobStore":
        root = Path(base_dir)
        root.mkdir(parents=True, exist_ok=True)
        store = cls(base_dir=root, _state=state, _artifacts=artifacts)
        store._ensure_backends(root)
        store._load_from_state()
        return store

    def _ensure_backends(self, base_dir: Path) -> None:
        root = Path(base_dir)
        root.mkdir(parents=True, exist_ok=True)
        if self.base_dir is None:
            self.base_dir = root
        if self._artifacts is None:
            from .persistence.fs_artifacts import FsArtifactStore

            self._artifacts = FsArtifactStore(self.base_dir)
        if self._state is None:
            from .persistence.json_state import JsonStateStore

            self._state = JsonStateStore(self.base_dir)

    def _require_state(self) -> StateStore:
        if self._state is None:
            if self.base_dir is None:
                raise RuntimeError("job store has no state backend")
            self._ensure_backends(self.base_dir)
        assert self._state is not None
        return self._state

    def _require_artifacts(self) -> ArtifactStore:
        if self._artifacts is None:
            if self.base_dir is None:
                raise RuntimeError("job store has no artifact backend")
            self._ensure_backends(self.base_dir)
        assert self._artifacts is not None
        return self._artifacts

    def _to_record(self, job: Job) -> JobRecord:
        return JobRecord(
            id=job.id,
            status=job.status,
            type=job.type,
            preview=job.preview,
            error=job.error,
            error_code=job.error_code,
            product_url=job.product_url,
            created_at=job.created_at,
            started_at=job.started_at,
            running_started_at=job.running_started_at,
            run_seconds=job.run_seconds,
            folder_label=job.folder_label,
            source_job_id=job.source_job_id,
            parent_job_id=job.parent_job_id,
            scrape_url=job.scrape_url,
            scrape_headers=job.scrape_headers,
            number=job.number,
            auto_publish=job.auto_publish,
            warnings=list(job.warnings or []),
            import_origin=infer_import_origin(
                import_origin=job.import_origin,
                job_type=job.type,
                parent_job_id=job.parent_job_id,
                scrape_url=job.scrape_url,
            ),
            user_edited=bool(job.user_edited),
            archived_at=job.archived_at,
            extra=parse_extra(job.extra),
            owner_id=job.owner_id,
        )

    def _to_job(
        self,
        record: JobRecord,
        events: Optional[List[JobEvent]] = None,
    ) -> Job:
        if events is None:
            events = self._require_state().list_events(record.id)
        artifact_id = record.source_job_id or record.id
        return Job(
            id=record.id,
            # Do not hydrate from GCS here: JobStore.load walks every job and
            # would download all album bytes before uvicorn can bind (Cloud Run).
            root=self._require_artifacts().local_root(
                artifact_id, owner_id=record.owner_id, hydrate=False
            ),
            status=record.status,
            type=record.type,
            preview=record.preview,
            error=record.error,
            error_code=parse_error_code(record.error_code),
            product_url=record.product_url,
            created_at=record.created_at,
            started_at=record.started_at,
            running_started_at=record.running_started_at,
            run_seconds=record.run_seconds,
            folder_label=record.folder_label,
            source_job_id=record.source_job_id,
            parent_job_id=record.parent_job_id,
            scrape_url=record.scrape_url,
            scrape_headers=record.scrape_headers,
            number=record.number,
            auto_publish=bool(record.auto_publish),
            warnings=list(record.warnings or []),
            import_origin=record.resolved_import_origin(),
            user_edited=bool(record.user_edited),
            archived_at=record.archived_at,
            extra=parse_extra(record.extra),
            owner_id=record.owner_id,
            events=list(events),
        )

    def get_meta(self, key: str) -> Optional[str]:
        state = self._state
        if state is None:
            if self.base_dir is None:
                return None
            self._ensure_backends(self.base_dir)
            state = self._state
        if state is None:
            return None
        return state.get_meta(key)

    def set_meta(self, key: str, value: str) -> None:
        self._require_state().set_meta(key, value)

    def _load_from_state(self) -> None:
        state = self._require_state()
        loaded: Dict[str, Job] = {}
        for record in state.list_all():
            try:
                events = state.list_events(record.id)
            except JobNotFoundError:
                events = []
            loaded[record.id] = self._to_job(record, events)
        with self._lock:
            self._jobs = loaded

    def create(
        self,
        base_dir: Path,
        *,
        folder_label: Optional[str] = None,
        job_type: str = TYPE_PREVIEW,
        parent_job_id: Optional[str] = None,
        source_job_id: Optional[str] = None,
        scrape_url: Optional[str] = None,
        scrape_headers: Optional[Dict[str, str]] = None,
        auto_publish: bool = False,
        import_origin: Optional[str] = None,
        owner_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Job:
        self._ensure_backends(Path(base_dir))
        resolved_type = str(job_type or TYPE_PREVIEW).strip().lower()
        if resolved_type not in _VALID_TYPES:
            raise ValueError(f"invalid job type: {job_type!r}")
        headers = None
        if scrape_headers:
            headers = {str(key): str(value) for key, value in scrape_headers.items()}
        job_id = str(uuid.uuid4())
        origin = infer_import_origin(
            import_origin=import_origin,
            job_type=resolved_type,
            parent_job_id=parent_job_id,
            scrape_url=scrape_url,
        )
        resolved_owner = owner_id
        if resolved_owner is None and parent_job_id:
            try:
                resolved_owner = self.get(parent_job_id).owner_id
            except JobNotFoundError:
                resolved_owner = None
        source = str(source_job_id).strip() if source_job_id else None
        if source == "":
            source = None
        record = JobRecord(
            id=job_id,
            status=STATUS_PENDING,
            type=resolved_type,
            folder_label=folder_label,
            source_job_id=source,
            parent_job_id=parent_job_id,
            scrape_url=scrape_url,
            scrape_headers=headers,
            number=self._require_state().allocate_number(),
            auto_publish=bool(auto_publish),
            import_origin=origin,
            owner_id=resolved_owner,
            extra=parse_extra(extra),
        )
        # Shared-artifact children reuse the source tree; skip empty ensure_job.
        if source is None:
            self._require_artifacts().ensure_job(job_id, owner_id=resolved_owner)
        self._require_state().create(record)
        job = self._to_job(record, events=[])
        with self._lock:
            self._jobs[job_id] = job
        return job

    def ensure_local_root(self, job_id: str) -> Path:
        """Hydrate a parse-ready album scratch pad; update ``job.root``.

        Remote (GCS) backends hydrate HTML + media placeholders, not full
        media bodies. Use ``ensure_artifact_file`` for real bytes.

        Hub fan-out children with ``extra.album_relpath`` get that subdirectory
        as ``job.root`` while artifacts stay on ``source_job_id``.
        """
        return self._album_root(job_id, hydrate=True)

    def staged_album_root(self, job_id: str) -> Path:
        """Local album tree without remote hydrate (keeps staged full media)."""
        return self._album_root(job_id, hydrate=False)

    def _album_root(self, job_id: str, *, hydrate: bool) -> Path:
        from .folder_hub import album_relpath_of

        with self._lock:
            job = self._require(job_id)
            artifact_id = job.source_job_id or job.id
            owner_id = job.owner_id
            album_rel = album_relpath_of(job)
        root = self._require_artifacts().local_root(
            artifact_id, owner_id=owner_id, hydrate=hydrate
        )
        if album_rel:
            root = root / album_rel
        with self._lock:
            self._require(job_id).root = root
        return root

    def ensure_artifact_file(self, job_id: str, relpath: str) -> Path:
        """Ensure one album file exists locally with real bytes."""
        from .folder_hub import artifact_relpath_for

        with self._lock:
            job = self._require(job_id)
            artifact_id = job.source_job_id or job.id
            owner_id = job.owner_id
            stored_rel = artifact_relpath_for(job, relpath)
        return self._require_artifacts().ensure_file(
            artifact_id, stored_rel, owner_id=owner_id
        )

    def put_album_file(
        self,
        job_id: str,
        relpath: str,
        path: Path,
        mtime: Optional[float] = None,
    ) -> None:
        """Stream one local file into the job's durable artifact store."""
        from .folder_hub import artifact_relpath_for

        with self._lock:
            job = self._require(job_id)
            artifact_id = job.source_job_id or job.id
            owner_id = job.owner_id
            stored_rel = artifact_relpath_for(job, relpath)
        self._require_artifacts().put_file(
            artifact_id,
            stored_rel,
            Path(path),
            mtime,
            owner_id=owner_id,
        )

    def stage_album_file(
        self,
        job_id: str,
        relpath: str,
        path: Path,
        mtime: Optional[float] = None,
    ) -> None:
        """Keep one album file on the local job tree without remote upload."""
        from .folder_hub import artifact_relpath_for

        with self._lock:
            job = self._require(job_id)
            artifact_id = job.source_job_id or job.id
            owner_id = job.owner_id
            stored_rel = artifact_relpath_for(job, relpath)
        self._require_artifacts().stage_file(
            artifact_id,
            stored_rel,
            Path(path),
            mtime,
            owner_id=owner_id,
        )

    def list_album_relpaths(self, job_id: str) -> List[str]:
        """Relative album artifact paths for a job (excludes state json)."""
        from .folder_hub import album_relpath_of

        with self._lock:
            job = self._require(job_id)
            artifact_id = job.source_job_id or job.id
            owner_id = job.owner_id
            album_rel = album_relpath_of(job)
        rels = self._require_artifacts().list(artifact_id, owner_id=owner_id)
        if not album_rel:
            return rels
        prefix = album_rel.replace("\\", "/").strip("/") + "/"
        trimmed: List[str] = []
        for rel in rels:
            text = rel.replace("\\", "/")
            if text.startswith(prefix):
                trimmed.append(text[len(prefix) :])
            elif text == album_rel.replace("\\", "/").strip("/"):
                continue
        return trimmed

    def retains_full_local_tree(self) -> bool:
        return self._require_artifacts().retains_full_local_tree

    def materialize_album(
        self,
        job_id: str,
        files: Iterable[tuple[str, bytes, Optional[float]]],
    ) -> Path:
        """Write album files through ArtifactStore (uploads to GCS when cloud)."""
        job = self.get(job_id)
        artifact_id = job.source_job_id or job.id
        root = self._require_artifacts().materialize(
            artifact_id, files, owner_id=job.owner_id
        )
        with self._lock:
            self._require(job_id).root = root
        return root

    def copy_artifacts(self, source_id: str, dest_id: str) -> None:
        """Copy album files from ``source_id`` to ``dest_id``.

        Does not copy ``job.json`` / ``events.json`` and does not mutate the
        source tree. Writes through ``ArtifactStore.materialize`` so GCS (and
        other remote backends) persist the destination, not only the local cache.
        """
        with self._lock:
            source = self._require(source_id)
            dest = self._require(dest_id)
        artifacts = self._require_artifacts()
        artifacts.ensure_job(dest_id, owner_id=dest.owner_id)
        src_root = artifacts.local_root(source_id, owner_id=source.owner_id)
        skip = {
            JOB_META_NAME,
            EVENTS_NAME,
            f"{JOB_META_NAME}.tmp",
            f"{EVENTS_NAME}.tmp",
        }
        if not src_root.is_dir():
            return
        files = []
        for path in src_root.rglob("*"):
            if not path.is_file() or path.name in skip:
                continue
            rel = path.relative_to(src_root).as_posix()
            files.append((rel, path.read_bytes(), path.stat().st_mtime))
        if files:
            artifacts.materialize(dest_id, files, owner_id=dest.owner_id)

    def create_upload_from(
        self,
        source_id: str,
        *,
        parent_job_id: Optional[str] = None,
    ) -> Job:
        with self._lock:
            source = self._require(source_id)
            if source.preview is None:
                raise ValueError("preview not ready")
            artifact_id = source.source_job_id or source.id
            snapshot = preview_from_dict(preview_to_dict(source.preview))
            if snapshot is None:
                raise ValueError("preview not ready")
            job_id = str(uuid.uuid4())
            origin = infer_import_origin(
                import_origin=source.import_origin,
                job_type=source.type,
                parent_job_id=source.parent_job_id,
                scrape_url=source.scrape_url,
            )
            record = JobRecord(
                id=job_id,
                status=STATUS_PENDING,
                type=TYPE_UPLOAD,
                preview=snapshot,
                folder_label=source.folder_label,
                source_job_id=artifact_id,
                parent_job_id=parent_job_id,
                number=self._require_state().allocate_number(),
                import_origin=origin,
                owner_id=source.owner_id,
            )
        self._require_state().create(record)
        job = self._to_job(record, events=[])
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str, *, owner_id: Optional[str] = None) -> Job:
        with self._lock:
            job = self._require(job_id)
            if (
                owner_id is not None
                and job.owner_id is not None
                and job.owner_id != owner_id
            ):
                raise JobNotFoundError(job_id)
            return job

    def list(
        self,
        *,
        include_archived: bool = False,
        owner_id: Optional[str] = None,
    ) -> List[Job]:
        with self._lock:
            jobs = [
                job
                for job in self._jobs.values()
                if (include_archived or job.archived_at is None)
                and (
                    owner_id is None
                    or job.owner_id is None
                    or job.owner_id == owner_id
                )
            ]
        jobs.sort(key=lambda job: (job.created_at, job.id), reverse=True)
        return jobs

    def list_children(self, parent_id: str) -> List[Job]:
        with self._lock:
            self._require(parent_id)
            children = [
                job for job in self._jobs.values() if job.parent_job_id == parent_id
            ]
        children.sort(key=lambda job: (job.created_at, job.id))
        return children

    def list_child_summaries(
        self,
        parent_id: str,
        *,
        include_archived: bool = False,
    ) -> List[Dict[str, Any]]:
        children = self.list_children(parent_id)
        if not include_archived:
            children = [child for child in children if child.archived_at is None]
        return summarize_jobs(
            children,
            all_jobs=self.list(include_archived=True),
        )

    def list_descendants(self, job_id: str) -> List[Job]:
        """All descendants excluding ``job_id`` itself."""
        with self._lock:
            self._require(job_id)
            ids = self._collect_descendant_ids_unlocked(job_id)
            descendants = []
            for cid in ids:
                if cid == job_id:
                    continue
                child = self._jobs.get(cid)
                if child is not None:
                    descendants.append(child)
        descendants.sort(key=lambda job: (job.created_at, job.id))
        return descendants

    def has_active_descendants(self, job_id: str) -> bool:
        return any(
            child.status in _ACTIVE_STATUSES for child in self.list_descendants(job_id)
        )

    def descendant_completion_warnings(self, job_id: str) -> List[str]:
        warnings: List[str] = []
        for child in self.list_descendants(job_id):
            label = f"#{child.number}" if child.number is not None else child.id
            if child.status == STATUS_FAILED:
                detail = (child.error or "").strip() or "failed"
                warnings.append(f"Child {label} failed: {detail}")
            elif child.status == STATUS_CANCELLED:
                warnings.append(f"Child {label} was cancelled")
        return warnings

    def list_cancellable_descendants(self, job_id: str) -> List[Job]:
        """Non-terminal descendants only (excludes ``job_id`` itself)."""
        with self._lock:
            self._require(job_id)
            ids = self._collect_descendant_ids_unlocked(job_id)
            descendants = []
            for cid in ids:
                if cid == job_id:
                    continue
                child = self._jobs.get(cid)
                if child is None or child.status in _TERMINAL_STATUSES:
                    continue
                descendants.append(child)
        descendants.sort(key=lambda job: (job.created_at, job.id))
        return descendants

    def cancel_preview_dict(self, job_id: str) -> Dict[str, Any]:
        job = self.get(job_id)
        descendants = self.list_cancellable_descendants(job_id)
        return {
            "job": job_summary_to_dict(job),
            "descendants": summarize_jobs(descendants, all_jobs=self.list()),
        }

    def restart_preview_dict(self, job_id: str) -> Dict[str, Any]:
        """Scrape children of a job, split into done vs remaining/failed."""
        job = self.get(job_id)
        scrape_children = [
            child for child in self.list_children(job_id) if child.type == TYPE_SCRAPE
        ]
        done = [child for child in scrape_children if child.status == STATUS_DONE]
        remaining = [
            child for child in scrape_children if child.status != STATUS_DONE
        ]
        all_jobs = self.list()
        return {
            "job": job_summary_to_dict(job),
            "descendants": summarize_jobs(scrape_children, all_jobs=all_jobs),
            "done": summarize_jobs(done, all_jobs=all_jobs),
            "remaining": summarize_jobs(remaining, all_jobs=all_jobs),
        }

    def update_extra(
        self,
        job_id: str,
        extra: Optional[Dict[str, Any]],
    ) -> Job:
        with self._lock:
            job = self._require(job_id)
            job.extra = parse_extra(extra)
            record = self._to_record(job)
        self._require_state().save(record)
        return job

    def list_albums(self, *, owner_id: Optional[str] = None) -> List[Job]:
        """One library album per gallery title, independent of job archive.

        Archived preview/upload runs still count so Saved albums stays
        visible after Hide. ``find_by_title`` still ignores archived rows
        so a new import of the same title is not a 409.
        """
        with self._lock:
            jobs = [
                job
                for job in self._jobs.values()
                if owner_id is None
                or job.owner_id is None
                or job.owner_id == owner_id
            ]
        grouped: Dict[str, List[Job]] = {}
        for job in jobs:
            if not _is_library_album(job):
                continue
            key = job_album_key(job)
            if key is None:
                continue
            grouped.setdefault(key, []).append(job)
        winners = [_pick_album_winner(group) for group in grouped.values()]
        winners.sort(key=lambda job: (job.created_at, job.id), reverse=True)
        return winners

    def list_album_summaries(
        self, *, owner_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        all_jobs = self.list(include_archived=True, owner_id=owner_id)
        preview_ids = _first_preview_child_ids(all_jobs)
        latest_url: Dict[str, str] = {}
        for job in all_jobs:
            key = job_album_key(job)
            if key and job.product_url and key not in latest_url:
                latest_url[key] = job.product_url
        summaries: List[Dict[str, Any]] = []
        for album in self.list_albums(owner_id=owner_id):
            summary = job_summary_to_dict(
                album, preview_job_id=preview_ids.get(album.id)
            )
            key = job_album_key(album)
            if key and not summary.get("product_url") and key in latest_url:
                summary["product_url"] = latest_url[key]
            summaries.append(summary)
        return summaries

    def find_by_title(
        self, title: str, *, owner_id: Optional[str] = None
    ) -> Optional[Job]:
        key = album_identity_key(title)
        if key is None:
            return None
        with self._lock:
            matches = [
                job
                for job in self._jobs.values()
                if job.archived_at is None
                and job_album_key(job) == key
                and (
                    owner_id is None
                    or job.owner_id is None
                    or job.owner_id == owner_id
                )
            ]
        if not matches:
            return None
        return _pick_album_winner(matches)

    def list_summaries(
        self,
        *,
        include_archived: bool = False,
        owner_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return summarize_jobs(
            self.list(include_archived=include_archived, owner_id=owner_id)
        )

    def detail_dict(
        self, job_id: str, *, owner_id: Optional[str] = None
    ) -> Dict[str, Any]:
        job = self.get(job_id, owner_id=owner_id)
        children = self.list_children(job_id)
        if owner_id is not None:
            children = [
                c
                for c in children
                if c.owner_id is None or c.owner_id == owner_id
            ]
        preview_child = next(
            (child for child in children if child.type == TYPE_PREVIEW),
            None,
        )
        return job_to_dict(
            job,
            child_ids=[child.id for child in children],
            preview_job_id=preview_child.id if preview_child else None,
        )

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._require(job_id)
            drop_ids = self._collect_dependent_ids(job_id)
            owners: Dict[str, Optional[str]] = {}
            for drop_id in drop_ids:
                job = self._jobs.get(drop_id)
                owners[drop_id] = job.owner_id if job is not None else None
                del self._jobs[drop_id]
                self._require_state().delete(drop_id)
        for drop_id in drop_ids:
            self._require_artifacts().delete_job(
                drop_id, owner_id=owners.get(drop_id)
            )

    def _collect_dependent_ids(self, job_id: str) -> List[str]:
        pending = [job_id]
        seen: List[str] = []
        seen_set = set()
        while pending:
            current = pending.pop()
            if current in seen_set:
                continue
            seen_set.add(current)
            seen.append(current)
            for other in self._jobs.values():
                if other.id in seen_set:
                    continue
                if other.source_job_id == current or other.parent_job_id == current:
                    pending.append(other.id)
        return seen

    def delete_duplicates_for_title(
        self, title: str, *, keep_id: str, owner_id: Optional[str] = None
    ) -> None:
        key = album_identity_key(title)
        if key is None:
            return
        with self._lock:
            keep = self._jobs.get(keep_id)
            scoped_owner = owner_id if owner_id is not None else (
                keep.owner_id if keep is not None else None
            )
            losers = [
                job.id
                for job in self._jobs.values()
                if job.id != keep_id
                and job.type == TYPE_PREVIEW
                and job_album_key(job) == key
                and (scoped_owner is None or job.owner_id == scoped_owner)
            ]
        for loser_id in losers:
            self.delete(loser_id)

    def set_preview(
        self,
        job_id: str,
        preview: AlbumPreview,
        *,
        warnings: Optional[List[str]] = None,
    ) -> Job:
        with self._lock:
            job = self._require(job_id)
            if job.status == STATUS_CANCELLED:
                return job
            job.preview = preview
            job.user_edited = False
            _apply_run_timing(job, STATUS_DONE)
            job.status = STATUS_DONE
            job.type = TYPE_PREVIEW
            job.error = None
            job.error_code = None
            if warnings is not None:
                job.warnings = parse_warnings(warnings)
            record = self._to_record(job)
        self._require_state().save(record)
        return job

    def set_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None,
        *,
        job_type: Optional[str] = None,
        warnings: Optional[List[str]] = None,
        error_code: Optional[str] = None,
    ) -> Job:
        with self._lock:
            job = self._require(job_id)
            if job.status == STATUS_CANCELLED and status in (
                STATUS_DONE,
                STATUS_FAILED,
            ):
                return job
            if status == STATUS_RUNNING:
                self._cancel_requested.discard(job_id)
            if status == STATUS_CANCELLED:
                self._cancel_requested.add(job_id)
            _apply_run_timing(job, status)
            job.status = status
            if job_type is not None:
                job.type = job_type
            job.error = error
            if status == STATUS_FAILED:
                job.error_code = parse_error_code(error_code)
            else:
                job.error_code = None
            if warnings is not None:
                job.warnings = parse_warnings(warnings)
            record = self._to_record(job)
        self._require_state().save(record)
        return job

    def update_preview(self, job_id: str, preview: AlbumPreview) -> Job:
        with self._lock:
            job = self._require(job_id)
            if job.status == STATUS_CANCELLED:
                return job
            if job.preview != preview:
                job.user_edited = True
            job.preview = preview
            _apply_run_timing(job, STATUS_DONE)
            job.status = STATUS_DONE
            job.type = TYPE_PREVIEW
            job.error = None
            job.error_code = None
            record = self._to_record(job)
        self._require_state().save(record)
        return job

    def mark_done(self, job_id: str, product_url: str) -> Job:
        with self._lock:
            job = self._require(job_id)
            if job.status == STATUS_CANCELLED:
                return job
            _apply_run_timing(job, STATUS_DONE)
            job.status = STATUS_DONE
            job.type = TYPE_UPLOAD
            job.product_url = product_url
            job.error = None
            job.error_code = None
            record = self._to_record(job)
        self._require_state().save(record)
        return job

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._cancel_requested:
                return True
            job = self._jobs.get(job_id)
            return job is not None and job.status == STATUS_CANCELLED

    def cancel_if_running(self, job_id: str) -> bool:
        """Mark a pending/running/waiting job cancelled. No-op if missing or already terminal."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in _TERMINAL_STATUSES:
                return False
            self._cancel_requested.add(job_id)
            _apply_run_timing(job, STATUS_CANCELLED)
            job.status = STATUS_CANCELLED
            job.error = None
            job.error_code = None
            record = self._to_record(job)
        self._require_state().save(record)
        return True

    def archive(self, job_id: str) -> List[str]:
        """Soft-delete a terminal job and its descendants.

        Sets ``archived_at`` (UTC ISO). Artifacts stay on disk/GCS. Raises
        ``JobNotFoundError`` or ``JobNotArchivableError`` if this job or any
        descendant is pending/running/waiting.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            self._require(job_id)
            ids = self._collect_descendant_ids_unlocked(job_id)
            targets: List[Job] = []
            for cid in ids:
                child = self._jobs.get(cid)
                if child is None:
                    continue
                if child.status in _ACTIVE_STATUSES:
                    raise JobNotArchivableError(cid)
                targets.append(child)
            records = []
            archived_ids: List[str] = []
            for child in targets:
                archived_ids.append(child.id)
                if child.archived_at is None:
                    child.archived_at = now
                    records.append(self._to_record(child))
        for record in records:
            self._require_state().save(record)
        return archived_ids

    def request_cancel(self, job_id: str) -> List[str]:
        """Cancel a pending/running/waiting job and non-terminal descendants.

        Returns ids newly marked cancelled. Raises ``JobNotFoundError`` or
        ``JobNotCancellableError`` (already done/failed/cancelled).
        """
        with self._lock:
            job = self._require(job_id)
            if job.status in _TERMINAL_STATUSES:
                raise JobNotCancellableError(job_id)
            ids = self._collect_descendant_ids_unlocked(job_id)
            newly: List[str] = []
            records = []
            for cid in ids:
                child = self._jobs.get(cid)
                if child is None or child.status in _TERMINAL_STATUSES:
                    continue
                self._cancel_requested.add(cid)
                child.status = STATUS_CANCELLED
                child.error = None
                child.error_code = None
                newly.append(cid)
                records.append(self._to_record(child))
        for record in records:
            self._require_state().save(record)
        return newly

    def _collect_descendant_ids_unlocked(self, job_id: str) -> List[str]:
        pending = [job_id]
        seen: List[str] = []
        seen_set = set()
        while pending:
            current = pending.pop()
            if current in seen_set:
                continue
            seen_set.add(current)
            seen.append(current)
            for other in self._jobs.values():
                if other.id in seen_set:
                    continue
                if other.parent_job_id == current:
                    pending.append(other.id)
        return seen

    def append_event(self, job_id: str, event: JobEvent) -> Job:
        with self._lock:
            job = self._require(job_id)
            job.events.append(event)
        self._require_state().append_event(job_id, event)
        return job

    def _require(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise JobNotFoundError(job_id) from exc
