"""StateStore: durable job *records* (metadata + SSE history), not album files."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...export.preview import AlbumPreview
from ..events import JobEvent

ORIGIN_FOLDER = "folder"
ORIGIN_WEB = "web"
_VALID_ORIGINS = frozenset({ORIGIN_FOLDER, ORIGIN_WEB})


def infer_import_origin(
    *,
    import_origin: Optional[str] = None,
    job_type: Optional[str] = None,
    parent_job_id: Optional[str] = None,
    scrape_url: Optional[str] = None,
) -> str:
    """Resolve durable album origin; infer legacy rows without the field."""
    if import_origin is not None:
        raw = str(import_origin).strip().lower()
        if raw in _VALID_ORIGINS:
            return raw
    if parent_job_id or scrape_url:
        return ORIGIN_WEB
    if str(job_type or "").strip().lower() == "scrape":
        return ORIGIN_WEB
    return ORIGIN_FOLDER


@dataclass
class JobRecord:
    """Job metadata persisted by a ``StateStore`` (no filesystem root, no events)."""

    id: str
    status: str
    type: str
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
    import_origin: Optional[str] = None
    user_edited: bool = False
    archived_at: Optional[datetime] = None
    extra: Optional[Dict[str, Any]] = None
    owner_id: Optional[str] = None

    def resolved_import_origin(self) -> str:
        origin = infer_import_origin(
            import_origin=self.import_origin,
            job_type=self.type,
            parent_job_id=self.parent_job_id,
            scrape_url=self.scrape_url,
        )
        self.import_origin = origin
        return origin


class StateStore(ABC):
    """Durable job records. Implementations take ``base_dir: Path`` (JOBS_ROOT)."""

    @abstractmethod
    def allocate_number(self) -> int:
        """Return the next monotonic job number and persist the counter."""

    @abstractmethod
    def create(self, record: JobRecord) -> JobRecord:
        """Insert a new job record. Does not persist events."""

    @abstractmethod
    def get(self, job_id: str, *, owner_id: Optional[str] = None) -> JobRecord:
        """Return one record (no events). Raises ``JobNotFoundError``.

        When ``owner_id`` is set, missing-or-other-owner looks like not found.
        """

    @abstractmethod
    def list_all(self, *, owner_id: Optional[str] = None) -> List[JobRecord]:
        """All records, no album-identity dedup. Optional owner filter."""

    @abstractmethod
    def save(self, record: JobRecord) -> JobRecord:
        """Replace job fields (not events). Raises ``JobNotFoundError``."""

    @abstractmethod
    def delete(self, job_id: str) -> None:
        """Remove the record and its events. Does not delete album files."""

    @abstractmethod
    def append_event(self, job_id: str, event: JobEvent) -> None:
        """Append one SSE/history event. Raises ``JobNotFoundError``."""

    @abstractmethod
    def list_events(self, job_id: str) -> List[JobEvent]:
        """Events in insert order. Raises ``JobNotFoundError`` if the job is missing."""

    @abstractmethod
    def get_meta(self, key: str) -> Optional[str]:
        """Return a persisted settings value, or ``None`` if missing."""

    @abstractmethod
    def set_meta(self, key: str, value: str) -> None:
        """Persist a settings key/value (survives restart)."""
