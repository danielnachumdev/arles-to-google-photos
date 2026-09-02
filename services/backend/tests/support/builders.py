"""Fluent builders for AlbumPreview / PreviewItem / JobRecord test data."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional, Sequence

from src.export.preview import AlbumJournal, AlbumPreview, PreviewItem
from src.jobs.persistence.state import JobRecord


class PreviewItemBuilder:
    """Build one immutable PreviewItem. Defaults match day1_mini."""

    def __init__(self) -> None:
        self._id = "20120802_01"
        self._relpath = "hrimages/20120802_01hr.JPG"
        self._caption = "hello"
        self._size_bytes = 16
        self._last_modified: Optional[datetime] = datetime(2012, 8, 2, 10, 0, 0)
        self._taken_on: Optional[date] = date(2012, 8, 2)
        self._kind: Optional[str] = None
        self._thumb_relpath: Optional[str] = None
        self._play_relpath: Optional[str] = None

    def with_id(self, item_id: str) -> "PreviewItemBuilder":
        self._id = item_id
        if "hrimages/" not in self._relpath.replace("\\", "/"):
            return self
        suffix = PathSuffix.from_relpath(self._relpath)
        self._relpath = f"hrimages/{item_id}hr{suffix}"
        return self

    def with_relpath(self, relpath: str) -> "PreviewItemBuilder":
        self._relpath = relpath
        return self

    def with_caption(self, caption: str) -> "PreviewItemBuilder":
        self._caption = caption
        return self

    def with_size(self, size_bytes: int) -> "PreviewItemBuilder":
        self._size_bytes = size_bytes
        return self

    def with_last_modified(
        self, stamp: Optional[datetime]
    ) -> "PreviewItemBuilder":
        self._last_modified = stamp
        return self

    def with_taken_on(self, taken: Optional[date]) -> "PreviewItemBuilder":
        self._taken_on = taken
        return self

    def as_video(
        self,
        *,
        relpath: str = "hrimages/0512_1_06[1]hr.wmv",
        thumb: Optional[str] = "thumbnails/TN_0512_1_06[1].jpg",
        play: Optional[str] = "preview/0512_1_06[1].mp4",
        item_id: str = "0512_1_06[1]",
    ) -> "PreviewItemBuilder":
        self._id = item_id
        self._relpath = relpath
        self._kind = "video"
        self._thumb_relpath = thumb
        self._play_relpath = play
        self._taken_on = None
        return self

    def build(self) -> PreviewItem:
        kwargs = {
            "id": self._id,
            "relpath": self._relpath,
            "caption": self._caption,
            "size_bytes": self._size_bytes,
            "last_modified": self._last_modified,
            "taken_on": self._taken_on,
        }
        if self._kind is not None:
            kwargs["kind"] = self._kind
        if self._thumb_relpath is not None:
            kwargs["thumb_relpath"] = self._thumb_relpath
        if self._play_relpath is not None:
            kwargs["play_relpath"] = self._play_relpath
        return PreviewItem(**kwargs)


class PathSuffix:
    @staticmethod
    def from_relpath(relpath: str) -> str:
        name = relpath.replace("\\", "/").rsplit("/", 1)[-1]
        if "." not in name:
            return ".JPG"
        return "." + name.rsplit(".", 1)[-1]


class PreviewBuilder:
    """Build an AlbumPreview. Default journal uses Hebrew placeholders."""

    def __init__(self) -> None:
        self._title = "Album"
        self._description: Optional[str] = "desc"
        self._multi_index = False
        self._items: Optional[Sequence[PreviewItem]] = None
        self._journal: Optional[AlbumJournal] = AlbumJournal(
            heading="יומן", paragraphs=("p1", "p2")
        )

    def with_title(self, title: str) -> "PreviewBuilder":
        self._title = title
        return self

    def with_description(self, description: Optional[str]) -> "PreviewBuilder":
        self._description = description
        return self

    def multi_index(self, value: bool = True) -> "PreviewBuilder":
        self._multi_index = value
        return self

    def with_items(self, *items: PreviewItem) -> "PreviewBuilder":
        self._items = items
        return self

    def with_journal(
        self, journal: Optional[AlbumJournal]
    ) -> "PreviewBuilder":
        self._journal = journal
        return self

    def no_journal(self) -> "PreviewBuilder":
        self._journal = None
        return self

    def build(self) -> AlbumPreview:
        items: Sequence[PreviewItem]
        if self._items is not None:
            items = self._items
        else:
            items = (PreviewItemBuilder().build(),)
        return AlbumPreview(
            title=self._title,
            description=self._description,
            multi_index=self._multi_index,
            items=tuple(items),
            journal=self._journal,
        )


class JobRecordBuilder:
    """Build a persistence JobRecord with sensible defaults."""

    def __init__(self) -> None:
        self._id = "job-1"
        self._status = "pending"
        self._type = "preview"
        self._preview: Optional[AlbumPreview] = None
        self._error: Optional[str] = None
        self._error_code: Optional[str] = None
        self._product_url: Optional[str] = None
        self._folder_label: Optional[str] = None
        self._created_at: Optional[datetime] = None
        self._started_at: Optional[datetime] = None
        self._running_started_at: Optional[datetime] = None
        self._run_seconds: Optional[float] = None
        self._source_job_id: Optional[str] = None
        self._parent_job_id: Optional[str] = None
        self._scrape_url: Optional[str] = None
        self._scrape_headers: Optional[dict[str, str]] = None
        self._auto_publish = False
        self._warnings: Optional[list[str]] = None
        self._import_origin: Optional[str] = None
        self._number: Optional[int] = None
        self._user_edited = False
        self._archived_at: Optional[datetime] = None
        self._extra: Optional[dict] = None
        self._owner_id: Optional[str] = None

    def with_id(self, job_id: str) -> "JobRecordBuilder":
        self._id = job_id
        return self

    def with_status(self, status: str) -> "JobRecordBuilder":
        self._status = status
        return self

    def with_type(self, job_type: str) -> "JobRecordBuilder":
        self._type = job_type
        return self

    def with_preview(self, preview: Optional[AlbumPreview]) -> "JobRecordBuilder":
        self._preview = preview
        return self

    def with_error(self, error: Optional[str]) -> "JobRecordBuilder":
        self._error = error
        return self

    def with_error_code(self, error_code: Optional[str]) -> "JobRecordBuilder":
        self._error_code = error_code
        return self

    def with_product_url(self, url: Optional[str]) -> "JobRecordBuilder":
        self._product_url = url
        return self

    def with_folder_label(self, label: Optional[str]) -> "JobRecordBuilder":
        self._folder_label = label
        return self

    def with_created_at(self, created_at: datetime) -> "JobRecordBuilder":
        self._created_at = created_at
        return self

    def with_started_at(self, started_at: Optional[datetime]) -> "JobRecordBuilder":
        self._started_at = started_at
        return self

    def with_running_started_at(
        self, running_started_at: Optional[datetime]
    ) -> "JobRecordBuilder":
        self._running_started_at = running_started_at
        return self

    def with_run_seconds(self, run_seconds: Optional[float]) -> "JobRecordBuilder":
        self._run_seconds = run_seconds
        return self

    def with_source_job_id(self, source_id: Optional[str]) -> "JobRecordBuilder":
        self._source_job_id = source_id
        return self

    def with_parent_job_id(self, parent_id: Optional[str]) -> "JobRecordBuilder":
        self._parent_job_id = parent_id
        return self

    def with_scrape(
        self,
        url: Optional[str],
        headers: Optional[dict[str, str]] = None,
    ) -> "JobRecordBuilder":
        self._scrape_url = url
        self._scrape_headers = headers
        return self

    def with_auto_publish(self, value: bool = True) -> "JobRecordBuilder":
        self._auto_publish = value
        return self

    def with_warnings(self, warnings: Optional[list[str]]) -> "JobRecordBuilder":
        self._warnings = warnings
        return self

    def with_import_origin(self, origin: Optional[str]) -> "JobRecordBuilder":
        self._import_origin = origin
        return self

    def with_number(self, number: Optional[int]) -> "JobRecordBuilder":
        self._number = number
        return self

    def with_user_edited(self, value: bool = True) -> "JobRecordBuilder":
        self._user_edited = value
        return self

    def with_archived_at(self, archived_at: Optional[datetime]) -> "JobRecordBuilder":
        self._archived_at = archived_at
        return self

    def with_extra(self, extra: Optional[dict]) -> "JobRecordBuilder":
        self._extra = extra
        return self

    def with_owner_id(self, owner_id: Optional[str]) -> "JobRecordBuilder":
        self._owner_id = owner_id
        return self

    def build(self) -> JobRecord:
        kwargs = {
            "id": self._id,
            "status": self._status,
            "type": self._type,
            "preview": self._preview,
            "error": self._error,
            "error_code": self._error_code,
            "product_url": self._product_url,
            "created_at": self._created_at
            or datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
            "started_at": self._started_at,
            "running_started_at": self._running_started_at,
            "run_seconds": self._run_seconds,
            "folder_label": self._folder_label,
            "source_job_id": self._source_job_id,
            "parent_job_id": self._parent_job_id,
            "scrape_url": self._scrape_url,
            "scrape_headers": self._scrape_headers,
            "auto_publish": self._auto_publish,
            "warnings": list(self._warnings or []),
            "import_origin": self._import_origin,
        }
        if self._number is not None:
            kwargs["number"] = self._number
        if self._user_edited:
            kwargs["user_edited"] = True
        if self._archived_at is not None:
            kwargs["archived_at"] = self._archived_at
        if self._extra is not None:
            kwargs["extra"] = self._extra
        if self._owner_id is not None:
            kwargs["owner_id"] = self._owner_id
        return JobRecord(**kwargs)
