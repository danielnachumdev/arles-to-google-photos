"""SQLAlchemy StateStore: local sqlite file or remote DATABASE_URL (Postgres, etc.).

SQLite does **not** speak ``gs://``. Pointing ``DATABASE_URL`` at a GCS URI
fails fast. When ``APP_ENV`` is cloud and ``DATABASE_URL`` is blank, the local
``{JOBS_ROOT}/migrator.sqlite`` file is mirrored to
``{GCS_PREFIX}/migrator.sqlite`` (see ``gcs_sqlite.py``). Uploads are
scheduled on a background thread (at most once per second); ``close``
flushes immediately. Last-writer-wins and only safe with one Cloud Run
instance / one uvicorn worker. Prefer Cloud SQL (``DATABASE_URL``) when
scaling out. Do not use GCS FUSE.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy import (
    create_engine,
    delete,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from ...export.preview import AlbumPreview
from ..events import JobEvent, event_from_dict
from ..store import (
    EVENTS_NAME,
    JOB_META_NAME,
    STATUS_DONE,
    TYPE_PREVIEW,
    JobNotFoundError,
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
from .job_numbers import META_NEXT_KEY, assign_missing_numbers, parse_job_number
from .json_state import load_events_file, record_from_meta
from .models import EVENTS_TABLE, JOBS_TABLE, META_TABLE
from .paths import validate_job_id
from .state import JobRecord, StateStore, infer_import_origin

DB_NAME = "migrator.sqlite"
_SQLITE_JOURNAL_MODES = frozenset({"WAL", "DELETE"})
_GCS_DATABASE_URL_ERROR = (
    "DATABASE_URL cannot be a GCS URI (gs:// or gcs://). "
    "SQLite does not speak gs://. Leave DATABASE_URL blank for local "
    "{JOBS_ROOT}/migrator.sqlite (mirrored to {GCS_PREFIX}/migrator.sqlite "
    "when APP_ENV is cloud), or use a SQLAlchemy URL such as "
    "postgresql+psycopg://… (Cloud SQL). Do not mount the bucket with GCS FUSE."
)
_GALLERY_TITLE_RE = re.compile(
    r'class=["\']gallerytitle["\'][^>]*>(.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)


def local_sqlite_url(base_dir: Path) -> str:
    """SQLAlchemy URL for ``{base_dir}/migrator.sqlite`` (posix path, 3 slashes)."""
    path = (Path(base_dir) / DB_NAME).resolve()
    return "sqlite:///" + path.as_posix()


def reject_gcs_database_url(url: str) -> None:
    """Raise if ``DATABASE_URL`` is ``gs://`` / ``gcs://`` (not a SQLAlchemy URL)."""
    lowered = str(url or "").strip().lower()
    if lowered.startswith("gs://") or lowered.startswith("gcs://"):
        raise ValueError(_GCS_DATABASE_URL_ERROR)


def _normalize_journal_mode(journal_mode: str) -> str:
    mode = str(journal_mode or "WAL").strip().upper()
    if mode not in _SQLITE_JOURNAL_MODES:
        raise ValueError(f"unsupported sqlite journal_mode: {journal_mode!r}")
    return mode


def create_engine_for_url(url: str, *, journal_mode: str = "WAL") -> Engine:
    """Engine with sqlite journal / busy_timeout, or pool_pre_ping for remote dialects.

    Default journal is WAL. Use DELETE when the sqlite file is mirrored to GCS
    so ``-wal`` / ``-shm`` sidecars do not need to be uploaded.
    """
    reject_gcs_database_url(url)
    lowered = str(url).strip().lower()
    is_sqlite = lowered.startswith("sqlite:")
    kwargs: Dict[str, Any] = {}
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 5.0}
        if ":memory:" in lowered:
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
        else:
            from sqlalchemy.pool import NullPool

            kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_pre_ping"] = True
    engine = create_engine(url, **kwargs)
    if is_sqlite:
        _attach_sqlite_pragmas(engine, journal_mode=_normalize_journal_mode(journal_mode))
    return engine


def _attach_sqlite_pragmas(engine: Engine, journal_mode: str = "WAL") -> None:
    mode = _normalize_journal_mode(journal_mode)
    synchronous = "FULL" if mode == "DELETE" else "NORMAL"

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn: Any, _connection_record: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute(f"PRAGMA journal_mode={mode}")
        cursor.execute(f"PRAGMA synchronous={synchronous}")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class SqlAlchemyStateStore(StateStore):
    """Job metadata via SQLAlchemy. Dialect comes from the URL (sqlite or postgres)."""

    def __init__(
        self,
        base_dir: Path,
        *,
        url: Optional[str] = None,
        engine: Optional[Engine] = None,
        sqlite_mirror: Optional[Any] = None,
        journal_mode: Optional[str] = None,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._sqlite_mirror = sqlite_mirror
        if sqlite_mirror is not None:
            sqlite_mirror.hydrate()
        if engine is not None:
            self._engine = engine
            self._url = str(url).strip() if url else str(engine.url)
        else:
            self._url = str(url or "").strip() or local_sqlite_url(self._base_dir)
            if journal_mode is not None:
                mode = journal_mode
            elif sqlite_mirror is not None:
                mode = "DELETE"
            else:
                mode = "WAL"
            self._engine = create_engine_for_url(self._url, journal_mode=mode)
        self._db_path = self._base_dir / DB_NAME
        # Schema via Alembic (fail closed). See migrate.upgrade_head.
        from .migrate import upgrade_head

        upgrade_head(self._engine)
        if self._is_sqlite:
            self._migrate_json_dirs()
            self._migrate_artifact_dirs()
        self._backfill_numbers()
        self._sync_sqlite()

    @property
    def url(self) -> str:
        return self._url

    @property
    def sqlite_mirror(self) -> Optional[Any]:
        return self._sqlite_mirror

    @property
    def _is_sqlite(self) -> bool:
        return str(self._engine.dialect.name) == "sqlite"

    def _sync_sqlite(self) -> None:
        mirror = self._sqlite_mirror
        if mirror is None:
            return
        mirror.schedule()

    def close(self) -> None:
        mirror = self._sqlite_mirror
        if mirror is not None:
            mirror.close()
        with self._lock:
            self._engine.dispose()

    def allocate_number(self) -> int:
        with self._lock:
            with self._engine.begin() as conn:
                value = self._allocate_unlocked(conn)
            self._sync_sqlite()
            return value

    def create(self, record: JobRecord) -> JobRecord:
        validate_job_id(record.id)
        if record.number is None:
            record.number = self.allocate_number()
        with self._lock:
            try:
                with self._engine.begin() as conn:
                    self._insert_job(conn, record)
            except IntegrityError as exc:
                raise ValueError(f"job already exists: {record.id}") from exc
            self._sync_sqlite()
        return record

    def get(self, job_id: str, *, owner_id: Optional[str] = None) -> JobRecord:
        validate_job_id(job_id)
        with self._lock:
            with self._engine.connect() as conn:
                query = select(JOBS_TABLE).where(JOBS_TABLE.c.id == job_id)
                row = conn.execute(query).mappings().first()
        if row is None:
            raise JobNotFoundError(job_id)
        record = self._record_from_mapping(row)
        if (
            owner_id is not None
            and record.owner_id is not None
            and record.owner_id != owner_id
        ):
            raise JobNotFoundError(job_id)
        return record

    def list_all(self, *, owner_id: Optional[str] = None) -> List[JobRecord]:
        with self._lock:
            with self._engine.connect() as conn:
                rows = conn.execute(select(JOBS_TABLE)).mappings().all()
        records: List[JobRecord] = []
        for row in rows:
            try:
                record = self._record_from_mapping(row)
            except (TypeError, ValueError, KeyError, json.JSONDecodeError):
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
        validate_job_id(record.id)
        with self._lock:
            with self._engine.begin() as conn:
                number = record.number
                if number is None:
                    row = conn.execute(
                        select(JOBS_TABLE.c.job_number).where(
                            JOBS_TABLE.c.id == record.id
                        )
                    ).mappings().first()
                    if row is None:
                        raise JobNotFoundError(record.id)
                    number = parse_job_number(row["job_number"])
                    record.number = number
                result = conn.execute(
                    update(JOBS_TABLE)
                    .where(JOBS_TABLE.c.id == record.id)
                    .values(**self._job_write_values(record, number=number))
                )
                if result.rowcount == 0:
                    raise JobNotFoundError(record.id)
            self._sync_sqlite()
        return record

    def delete(self, job_id: str) -> None:
        validate_job_id(job_id)
        with self._lock:
            with self._engine.begin() as conn:
                result = conn.execute(
                    delete(JOBS_TABLE).where(JOBS_TABLE.c.id == job_id)
                )
                if result.rowcount == 0:
                    raise JobNotFoundError(job_id)
            self._sync_sqlite()

    def append_event(self, job_id: str, event: JobEvent) -> None:
        validate_job_id(job_id)
        with self._lock:
            with self._engine.begin() as conn:
                exists = conn.execute(
                    select(JOBS_TABLE.c.id).where(JOBS_TABLE.c.id == job_id)
                ).first()
                if exists is None:
                    raise JobNotFoundError(job_id)
                self._insert_event(conn, event)
            self._sync_sqlite()

    def list_events(self, job_id: str) -> List[JobEvent]:
        validate_job_id(job_id)
        with self._lock:
            with self._engine.connect() as conn:
                exists = conn.execute(
                    select(JOBS_TABLE.c.id).where(JOBS_TABLE.c.id == job_id)
                ).first()
                if exists is None:
                    raise JobNotFoundError(job_id)
                rows = conn.execute(
                    select(EVENTS_TABLE)
                    .where(EVENTS_TABLE.c.job_id == job_id)
                    .order_by(EVENTS_TABLE.c.id.asc())
                ).mappings().all()
        events: List[JobEvent] = []
        for row in rows:
            extra_raw = row.get("extra_json")
            extra: Any = None
            if extra_raw:
                try:
                    extra = json.loads(str(extra_raw))
                except (TypeError, ValueError, json.JSONDecodeError):
                    extra = None
                if extra is not None and not isinstance(extra, dict):
                    extra = None
            events.append(
                event_from_dict(
                    {
                        "job_id": row.get("job_id"),
                        "stage": row.get("stage"),
                        "message": row.get("message") or "",
                        "current": row.get("current") or 0,
                        "total": row.get("total") or 0,
                        "extra": extra,
                        "occurred_at": row.get("occurred_at"),
                        "kind": row.get("kind"),
                        "audience": row.get("audience"),
                    },
                    default_job_id=job_id,
                )
            )
        return events

    def _job_write_values(
        self, record: JobRecord, *, number: Optional[int]
    ) -> Dict[str, Any]:
        archived_at = None
        if record.archived_at is not None:
            archived_at = record.archived_at.isoformat()
        return {
            "type": record.type,
            "status": record.status,
            "error": record.error,
            "error_code": parse_error_code(record.error_code),
            "product_url": record.product_url,
            "created_at": record.created_at.isoformat(),
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "running_started_at": (
                record.running_started_at.isoformat() if record.running_started_at else None
            ),
            "run_seconds": record.run_seconds,
            "folder_label": record.folder_label,
            "preview_json": self._preview_json(record),
            "source_job_id": record.source_job_id,
            "parent_job_id": record.parent_job_id,
            "scrape_url": record.scrape_url,
            "scrape_headers_json": self._headers_json(record),
            "job_number": number,
            "auto_publish": 1 if record.auto_publish else 0,
            "warnings_json": self._warnings_json(record),
            "import_origin": record.resolved_import_origin(),
            "extra_json": self._extra_json(record),
            "user_edited": 1 if record.user_edited else 0,
            "archived_at": archived_at,
            "owner_id": record.owner_id,
        }

    def _insert_job(self, conn: Any, record: JobRecord) -> None:
        conn.execute(
            insert(JOBS_TABLE).values(
                id=record.id,
                **self._job_write_values(record, number=record.number),
            )
        )

    def _insert_event(self, conn: Any, event: JobEvent) -> None:
        extra_json: Optional[str] = None
        if event.extra is not None:
            extra_json = json.dumps(event.extra, ensure_ascii=False)
        owner_id = None
        job_row = conn.execute(
            select(JOBS_TABLE.c.owner_id).where(JOBS_TABLE.c.id == event.job_id)
        ).mappings().first()
        if job_row is not None and job_row.get("owner_id"):
            owner_id = str(job_row["owner_id"])
        conn.execute(
            insert(EVENTS_TABLE).values(
                job_id=event.job_id,
                stage=event.stage,
                message=event.message,
                current=int(event.current),
                total=int(event.total),
                extra_json=extra_json,
                occurred_at=event.occurred_at.isoformat(),
                kind=event.kind,
                audience=event.audience,
                owner_id=owner_id,
            )
        )

    def _preview_json(self, record: JobRecord) -> Optional[str]:
        payload = preview_to_dict(record.preview)
        if payload is None:
            return None
        return json.dumps(payload, ensure_ascii=False)

    def _headers_json(self, record: JobRecord) -> Optional[str]:
        if not record.scrape_headers:
            return None
        return json.dumps(record.scrape_headers, ensure_ascii=False)

    def _warnings_json(self, record: JobRecord) -> Optional[str]:
        if not record.warnings:
            return None
        return json.dumps(list(record.warnings), ensure_ascii=False)

    def _extra_json(self, record: JobRecord) -> Optional[str]:
        extra = parse_extra(record.extra)
        if not extra:
            return None
        return json.dumps(extra, ensure_ascii=False)

    def _user_edited_from_mapping(self, row: Mapping[str, Any]) -> bool:
        return parse_user_edited(row.get("user_edited"))

    def _error_code_from_mapping(self, row: Mapping[str, Any]) -> Optional[str]:
        return parse_error_code(row.get("error_code"))

    def _extra_from_mapping(self, row: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        raw = row.get("extra_json")
        if not raw:
            return None
        try:
            parsed = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return parse_extra(parsed)

    def _warnings_from_mapping(self, row: Mapping[str, Any]) -> List[str]:
        raw = row.get("warnings_json")
        if not raw:
            return []
        try:
            parsed = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        return parse_warnings(parsed)

    def _headers_from_mapping(self, row: Mapping[str, Any]) -> Optional[Dict[str, str]]:
        raw = row.get("scrape_headers_json")
        if not raw:
            return None
        try:
            parsed = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(parsed, dict) or not parsed:
            return None
        return {str(key): str(value) for key, value in parsed.items()}

    def _record_from_mapping(self, row: Mapping[str, Any]) -> JobRecord:
        preview = None
        raw_preview = row.get("preview_json")
        if raw_preview:
            preview = preview_from_dict(json.loads(str(raw_preview)))
        source_raw = row.get("source_job_id")
        source_job_id = str(source_raw) if source_raw else None
        parent_raw = row.get("parent_job_id")
        parent_job_id = str(parent_raw) if parent_raw else None
        scrape_url_raw = row.get("scrape_url")
        scrape_url = str(scrape_url_raw) if scrape_url_raw else None
        import_origin = infer_import_origin(
            import_origin=str(row["import_origin"]) if row.get("import_origin") else None,
            job_type=str(row["type"]),
            parent_job_id=parent_job_id,
            scrape_url=scrape_url,
        )
        return JobRecord(
            id=str(row["id"]),
            status=str(row["status"]),
            type=str(row["type"]),
            preview=preview,
            error=row.get("error"),
            error_code=self._error_code_from_mapping(row),
            product_url=row.get("product_url"),
            created_at=parse_created_at(row.get("created_at")),
            started_at=parse_optional_datetime(row.get("started_at")),
            running_started_at=parse_optional_datetime(row.get("running_started_at")),
            run_seconds=parse_run_seconds(row.get("run_seconds")),
            folder_label=row.get("folder_label"),
            source_job_id=source_job_id,
            parent_job_id=parent_job_id,
            scrape_url=scrape_url,
            scrape_headers=self._headers_from_mapping(row),
            number=parse_job_number(row.get("job_number")),
            auto_publish=bool(row.get("auto_publish")),
            warnings=self._warnings_from_mapping(row),
            import_origin=import_origin,
            user_edited=self._user_edited_from_mapping(row),
            archived_at=parse_optional_datetime(row.get("archived_at")),
            extra=self._extra_from_mapping(row),
            owner_id=str(row["owner_id"]) if row.get("owner_id") else None,
        )

    def _migrate_json_dirs(self) -> None:
        if not self._base_dir.is_dir():
            return
        with self._lock:
            with self._engine.begin() as conn:
                existing = {
                    str(row["id"])
                    for row in conn.execute(select(JOBS_TABLE.c.id)).mappings().all()
                }
                for child in self._base_dir.iterdir():
                    if not child.is_dir():
                        continue
                    meta_path = child / JOB_META_NAME
                    if not meta_path.is_file():
                        continue
                    try:
                        data = json.loads(meta_path.read_text(encoding="utf-8"))
                        if not isinstance(data, dict):
                            continue
                        record = record_from_meta(data, fallback_id=child.name)
                    except (
                        OSError,
                        json.JSONDecodeError,
                        TypeError,
                        ValueError,
                        KeyError,
                    ):
                        continue
                    if record.id in existing:
                        continue
                    self._insert_job(conn, record)
                    for event in load_events_file(child / EVENTS_NAME, record.id):
                        self._insert_event(conn, event)
                    existing.add(record.id)

    def _migrate_artifact_dirs(self) -> None:
        """Register album trees that predate ``job.json`` so they stay visible."""
        if not self._base_dir.is_dir():
            return
        with self._lock:
            with self._engine.begin() as conn:
                existing = {
                    str(row["id"])
                    for row in conn.execute(select(JOBS_TABLE.c.id)).mappings().all()
                }
                for child in self._base_dir.iterdir():
                    if not child.is_dir():
                        continue
                    try:
                        job_id = validate_job_id(child.name)
                    except ValueError:
                        continue
                    if job_id in existing:
                        continue
                    index_path = child / "index.html"
                    if not index_path.is_file():
                        continue
                    title = _title_from_index(index_path) or job_id
                    record = JobRecord(
                        id=job_id,
                        status=STATUS_DONE,
                        type=TYPE_PREVIEW,
                        preview=AlbumPreview(
                            title=title,
                            description=None,
                            multi_index=False,
                            items=(),
                        ),
                        folder_label=None,
                    )
                    self._insert_job(conn, record)
                    existing.add(job_id)

    def _allocate_unlocked(self, conn: Any) -> int:
        row = conn.execute(
            select(META_TABLE.c.value).where(META_TABLE.c.key == META_NEXT_KEY)
        ).mappings().first()
        next_value = parse_job_number(row["value"] if row is not None else None) or 1
        self._set_next_unlocked(conn, next_value + 1)
        return next_value

    def _set_next_unlocked(self, conn: Any, next_value: int) -> None:
        self._upsert_meta(conn, META_NEXT_KEY, str(max(int(next_value), 1)))

    def _peek_next_unlocked(self, conn: Any) -> int:
        row = conn.execute(
            select(META_TABLE.c.value).where(META_TABLE.c.key == META_NEXT_KEY)
        ).mappings().first()
        return parse_job_number(row["value"] if row is not None else None) or 1

    def _upsert_meta(self, conn: Any, key: str, value: str) -> None:
        existing = conn.execute(
            select(META_TABLE.c.key).where(META_TABLE.c.key == str(key))
        ).first()
        if existing is None:
            conn.execute(insert(META_TABLE).values(key=str(key), value=str(value)))
        else:
            conn.execute(
                update(META_TABLE)
                .where(META_TABLE.c.key == str(key))
                .values(value=str(value))
            )

    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            with self._engine.connect() as conn:
                row = conn.execute(
                    select(META_TABLE.c.value).where(META_TABLE.c.key == str(key))
                ).mappings().first()
        if row is None:
            return None
        return str(row["value"])

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            with self._engine.begin() as conn:
                self._upsert_meta(conn, str(key), str(value))
            self._sync_sqlite()

    def _backfill_numbers(self) -> None:
        records = self.list_all()
        with self._lock:
            with self._engine.begin() as conn:
                persisted = self._peek_next_unlocked(conn)
                assigned, next_value = assign_missing_numbers(records, persisted)
                for record in assigned:
                    conn.execute(
                        update(JOBS_TABLE)
                        .where(JOBS_TABLE.c.id == record.id)
                        .values(job_number=record.number)
                    )
                self._set_next_unlocked(conn, next_value)


def _title_from_index(index_path: Path) -> Optional[str]:
    try:
        text_html = index_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _GALLERY_TITLE_RE.search(text_html)
    if match is None:
        return None
    title = " ".join(
        match.group(1).replace("&nbsp;", " ").replace("\xa0", " ").split()
    )
    return title or None


# Local sqlite under JOBS_ROOT; same class, default URL.
SqliteStateStore = SqlAlchemyStateStore
