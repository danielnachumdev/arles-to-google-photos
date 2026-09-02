"""TDD: StateStore Protocol — json + sqlite backends (records + events only)."""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.export.preview import AlbumPreview
from src.jobs.events import JobEvent
from src.jobs.persistence.json_state import JsonStateStore
from src.jobs.persistence.sqlalchemy_state import SqlAlchemyStateStore
from src.jobs.persistence.sqlite_state import SqliteStateStore
from src.jobs.persistence.state import JobRecord, StateStore
from src.jobs.store import EVENTS_NAME, JOB_META_NAME, JobNotFoundError
from tests.support.builders import JobRecordBuilder, PreviewBuilder, PreviewItemBuilder
from tests.support.persistence import StateStoreBackend, state_store_backends

BACKENDS = state_store_backends()


def _preview(title: str = "Album") -> AlbumPreview:
    return PreviewBuilder().with_title(title).build()


def _record(
    job_id: str = "job-1",
    *,
    status: str = "pending",
    job_type: str = "preview",
    preview: AlbumPreview | None = None,
    error: str | None = None,
    product_url: str | None = None,
    folder_label: str | None = None,
    created_at: datetime | None = None,
    source_job_id: str | None = None,
    parent_job_id: str | None = None,
    scrape_url: str | None = None,
    scrape_headers: dict[str, str] | None = None,
    auto_publish: bool = False,
    warnings: list[str] | None = None,
    import_origin: str | None = None,
) -> JobRecord:
    builder = (
        JobRecordBuilder()
        .with_id(job_id)
        .with_status(status)
        .with_type(job_type)
        .with_preview(preview)
        .with_error(error)
        .with_product_url(product_url)
        .with_folder_label(folder_label)
        .with_source_job_id(source_job_id)
        .with_parent_job_id(parent_job_id)
        .with_scrape(scrape_url, scrape_headers)
        .with_auto_publish(auto_publish)
        .with_warnings(warnings)
        .with_import_origin(import_origin)
    )
    if created_at is not None:
        builder.with_created_at(created_at)
    return builder.build()


@pytest.fixture(params=BACKENDS, ids=lambda backend: backend.name)
def state(request: pytest.FixtureRequest, tmp_path: Path) -> StateStore:
    backend = request.param
    assert isinstance(backend, StateStoreBackend)
    return backend.create(tmp_path)






































class TestStateStoreContract:
    def test_state_store_is_protocol(self) -> None:
        assert issubclass(JsonStateStore, StateStore)
        assert issubclass(SqlAlchemyStateStore, StateStore)
        assert issubclass(SqliteStateStore, StateStore)
        assert SqliteStateStore is SqlAlchemyStateStore

    def test_meta_roundtrip(self, state: StateStore) -> None:
        assert state.get_meta("max_concurrent_jobs") is None
        state.set_meta("max_concurrent_jobs", "5")
        assert state.get_meta("max_concurrent_jobs") == "5"
        state.set_meta("max_concurrent_jobs", "2")
        assert state.get_meta("max_concurrent_jobs") == "2"

    def test_create_get_roundtrip(self, state: StateStore) -> None:
        created = state.create(_record(preview=_preview("Day 1"), folder_label="Day1"))
        fetched = state.get("job-1")

        assert created.id == "job-1"
        assert fetched.id == "job-1"
        assert fetched.number == 1
        assert created.number == 1
        assert fetched.status == "pending"
        assert fetched.type == "preview"
        assert fetched.folder_label == "Day1"
        assert fetched.source_job_id is None
        assert fetched.preview is not None
        assert fetched.preview.title == "Day 1"
        assert fetched.preview.journal is not None
        assert fetched.preview.journal.heading == "יומן"
        assert fetched.preview.items[0].taken_on == date(2012, 8, 2)
        assert fetched.preview.items[0].kind == "image"
        assert fetched.preview.items[0].thumb_relpath is None
        assert fetched.preview.items[0].play_relpath is None
        assert fetched.error_code is None

    def test_error_code_roundtrip(self, state: StateStore) -> None:
        state.create(
            _record(status="failed", error="Not a supported Arles album: https://albums.example/x")
        )
        created = state.get("job-1")
        created.error_code = "not_arles"
        state.save(created)
        fetched = state.get("job-1")
        assert fetched.status == "failed"
        assert fetched.error_code == "not_arles"
        assert "Arles" in (fetched.error or "")

    def test_preview_video_fields_roundtrip(self, state: StateStore) -> None:
        preview = (
            PreviewBuilder()
            .with_title("May video")
            .with_description(None)
            .no_journal()
            .with_items(
                PreviewItemBuilder()
                .as_video()
                .with_caption("clip")
                .with_size(99)
                .with_last_modified(datetime(2012, 5, 12, 10, 0, 0))
                .build()
            )
            .build()
        )
        state.create(_record(preview=preview, folder_label="May"))
        fetched = state.get("job-1")
        assert fetched.preview is not None
        item = fetched.preview.items[0]
        assert item.kind == "video"
        assert item.thumb_relpath == "thumbnails/TN_0512_1_06[1].jpg"
        assert item.play_relpath == "preview/0512_1_06[1].mp4"
        assert item.relpath == "hrimages/0512_1_06[1]hr.wmv"

    def test_preview_from_dict_infers_video_kind_for_legacy_jobs(self) -> None:
        from src.jobs.store import preview_from_dict

        preview = preview_from_dict(
            {
                "title": "Legacy",
                "description": None,
                "multi_index": False,
                "items": [
                    {
                        "id": "clip01",
                        "relpath": "hrimages/clip01hr.wmv",
                        "caption": "",
                        "size_bytes": 12,
                    }
                ],
            }
        )
        assert preview is not None
        assert preview.items[0].kind == "video"
        assert preview.items[0].thumb_relpath is None
        assert preview.items[0].play_relpath is None

    def test_waiting_and_warnings_roundtrip(self, state: StateStore) -> None:
        state.create(
            _record(
                "hub-1",
                status="waiting",
                job_type="scrape",
                folder_label="albums.example",
                scrape_url="https://albums.example/hub",
                warnings=["Child #3 failed: site down"],
            )
        )
        fetched = state.get("hub-1")
        assert fetched.status == "waiting"
        assert fetched.warnings == ["Child #3 failed: site down"]
        state.save(
            _record(
                "hub-1",
                status="done",
                job_type="scrape",
                folder_label="albums.example",
                scrape_url="https://albums.example/hub",
                warnings=["Child #3 failed: site down", "Child #4 was cancelled"],
            )
        )
        updated = state.get("hub-1")
        assert updated.status == "done"
        assert updated.warnings == [
            "Child #3 failed: site down",
            "Child #4 was cancelled",
        ]

    def test_auto_publish_roundtrip(self, state: StateStore) -> None:
        state.create(_record(auto_publish=True, folder_label="Day1"))
        fetched = state.get("job-1")
        assert fetched.auto_publish is True
        state.save(
            _record(
                status="done",
                job_type="preview",
                preview=_preview("Day 1"),
                folder_label="Day1",
                auto_publish=True,
            )
        )
        updated = state.get("job-1")
        assert updated.auto_publish is True
        assert updated.status == "done"

    def test_source_job_id_roundtrip(self, state: StateStore) -> None:
        state.create(
            _record(
                "upload-1",
                status="running",
                job_type="upload",
                preview=_preview("Day 1"),
                folder_label="Day1",
            )
        )
        record = state.get("upload-1")
        updated = JobRecord(
            id=record.id,
            status=record.status,
            type=record.type,
            preview=record.preview,
            error=record.error,
            product_url=record.product_url,
            created_at=record.created_at,
            folder_label=record.folder_label,
            source_job_id="preview-1",
        )
        state.save(updated)
        fetched = state.get("upload-1")
        assert fetched.source_job_id == "preview-1"

    def test_run_timing_roundtrip(self, state: StateStore) -> None:
        started = datetime(2026, 8, 8, 10, 0, 30, tzinfo=timezone.utc)
        running_started = datetime(2026, 8, 8, 10, 1, 0, tzinfo=timezone.utc)
        state.create(
            JobRecordBuilder()
            .with_id("job-run")
            .with_status("running")
            .with_started_at(started)
            .with_running_started_at(running_started)
            .with_run_seconds(12.5)
            .build()
        )
        fetched = state.get("job-run")
        assert fetched.started_at == started
        assert fetched.running_started_at == running_started
        assert fetched.run_seconds == 12.5
        listed = {row.id: row for row in state.list_all()}
        assert listed["job-run"].started_at == started
        assert listed["job-run"].running_started_at == running_started
        assert listed["job-run"].run_seconds == 12.5

        updated = JobRecord(
            id=fetched.id,
            status="done",
            type=fetched.type,
            preview=fetched.preview,
            error=fetched.error,
            product_url=fetched.product_url,
            created_at=fetched.created_at,
            started_at=started,
            running_started_at=None,
            run_seconds=18.0,
            folder_label=fetched.folder_label,
        )
        state.save(updated)
        saved = state.get("job-run")
        assert saved.status == "done"
        assert saved.started_at == started
        assert saved.running_started_at is None
        assert saved.run_seconds == 18.0

    def test_archived_at_roundtrip(self, state: StateStore) -> None:
        stamp = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
        state.create(_record("job-arch", status="done", preview=_preview("Day 1")))
        record = state.get("job-arch")
        assert record.archived_at is None
        updated = JobRecord(
            id=record.id,
            status=record.status,
            type=record.type,
            preview=record.preview,
            error=record.error,
            product_url=record.product_url,
            created_at=record.created_at,
            folder_label=record.folder_label,
            archived_at=stamp,
        )
        state.save(updated)
        fetched = state.get("job-arch")
        assert fetched.archived_at == stamp
        listed = {row.id: row for row in state.list_all()}
        assert listed["job-arch"].archived_at == stamp

    def test_user_edited_roundtrip(self, state: StateStore) -> None:
        state.create(_record("job-edit", status="done", preview=_preview("Day 1")))
        record = state.get("job-edit")
        assert record.user_edited is False
        updated = JobRecord(
            id=record.id,
            status=record.status,
            type=record.type,
            preview=record.preview,
            error=record.error,
            product_url=record.product_url,
            created_at=record.created_at,
            folder_label=record.folder_label,
            user_edited=True,
        )
        state.save(updated)
        fetched = state.get("job-edit")
        assert fetched.user_edited is True

    def test_job_extra_roundtrip(self, state: StateStore) -> None:
        state.create(
            _record(
                "scrape-extra",
                status="pending",
                job_type="scrape",
                scrape_url="https://albums.example/hub",
            )
        )
        record = state.get("scrape-extra")
        updated = JobRecord(
            id=record.id,
            status=record.status,
            type=record.type,
            preview=record.preview,
            error=record.error,
            product_url=record.product_url,
            created_at=record.created_at,
            folder_label=record.folder_label,
            source_job_id=record.source_job_id,
            parent_job_id=record.parent_job_id,
            scrape_url=record.scrape_url,
            scrape_headers=record.scrape_headers,
            number=record.number,
            auto_publish=record.auto_publish,
            warnings=list(record.warnings or []),
            import_origin=record.import_origin,
            extra={
                "restarted_from": "old-hub",
                "skip_done_urls": ["https://albums.example/day1"],
            },
        )
        state.save(updated)
        fetched = state.get("scrape-extra")
        assert fetched.extra == {
            "restarted_from": "old-hub",
            "skip_done_urls": ["https://albums.example/day1"],
        }

    def test_scrape_parent_and_headers_roundtrip(self, state: StateStore) -> None:
        state.create(
            _record(
                "scrape-1",
                status="running",
                job_type="scrape",
                folder_label="example.com",
                scrape_url="https://example.com/album",
                scrape_headers={"Cookie": "secret=1", "Authorization": "Bearer tok"},
            )
        )
        fetched = state.get("scrape-1")
        assert fetched.type == "scrape"
        assert fetched.parent_job_id is None
        assert fetched.scrape_url == "https://example.com/album"
        assert fetched.scrape_headers == {
            "Cookie": "secret=1",
            "Authorization": "Bearer tok",
        }

        state.create(
            _record(
                "child-1",
                status="pending",
                job_type="preview",
                parent_job_id="scrape-1",
            )
        )
        child = state.get("child-1")
        assert child.parent_job_id == "scrape-1"
        assert child.scrape_url is None
        assert child.scrape_headers is None

        state.save(
            _record(
                "scrape-1",
                status="done",
                job_type="scrape",
                folder_label="example.com",
                scrape_url="https://example.com/album",
                scrape_headers={"Cookie": "secret=1"},
                parent_job_id=None,
            )
        )
        updated = state.get("scrape-1")
        assert updated.status == "done"
        assert updated.type == "scrape"
        assert updated.scrape_headers == {"Cookie": "secret=1"}

    def test_get_missing_raises(self, state: StateStore) -> None:
        with pytest.raises(JobNotFoundError):
            state.get("missing")

    def test_save_updates_status_type_preview_and_error(self, state: StateStore) -> None:
        state.create(_record())
        state.save(
            _record(
                status="running",
                job_type="upload",
                preview=_preview("Edited"),
                error="boom",
                product_url="https://photos.example/a",
                folder_label="Day1",
            )
        )
        fetched = state.get("job-1")
        assert fetched.status == "running"
        assert fetched.type == "upload"
        assert fetched.error == "boom"
        assert fetched.product_url == "https://photos.example/a"
        assert fetched.folder_label == "Day1"
        assert fetched.preview is not None
        assert fetched.preview.title == "Edited"

    def test_list_all_returns_every_job(self, state: StateStore) -> None:
        state.create(_record("a", preview=_preview("A")))
        state.create(_record("b", preview=_preview("A")))
        ids = {record.id for record in state.list_all()}
        assert ids == {"a", "b"}

    def test_append_and_list_events_in_order(self, state: StateStore) -> None:
        state.create(_record())
        first = JobEvent(
            job_id="job-1",
            stage="ingest",
            message="Writing upload",
            current=0,
            total=2,
            extra={"items": 1},
            occurred_at=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
        )
        second = JobEvent(
            job_id="job-1",
            stage="preview_ready",
            message="Day 1",
            current=2,
            total=2,
            extra={"title": "Day 1"},
            occurred_at=datetime(2024, 6, 1, 12, 0, 5, tzinfo=timezone.utc),
        )
        state.append_event("job-1", first)
        state.append_event("job-1", second)

        events = state.list_events("job-1")
        assert [event.stage for event in events] == ["ingest", "preview_ready"]
        assert events[0].message == "Writing upload"
        assert events[0].current == 0
        assert events[0].total == 2
        assert events[0].extra == {"items": 1}
        assert events[0].occurred_at == first.occurred_at
        assert events[0].kind == "log"
        assert events[0].audience == "ui"
        assert events[1].extra == {"title": "Day 1"}
        assert events[1].kind == "lifecycle"
        assert events[1].audience == "ui"

    def test_append_event_missing_job_raises(self, state: StateStore) -> None:
        with pytest.raises(JobNotFoundError):
            state.append_event(
                "missing", JobEvent(job_id="missing", stage="error", message="nope")
            )

    def test_delete_removes_record_and_events_not_album_files(
        self,
        state: StateStore, tmp_path: Path
    ) -> None:
        state.create(_record())
        state.append_event("job-1", JobEvent(job_id="job-1", stage="ingest"))
        album = tmp_path / "job-1" / "index.html"
        album.parent.mkdir(parents=True, exist_ok=True)
        album.write_text("<html></html>", encoding="utf-8")

        state.delete("job-1")

        with pytest.raises(JobNotFoundError):
            state.get("job-1")
        assert state.list_all() == []
        assert album.is_file()

    def test_delete_missing_raises(self, state: StateStore) -> None:
        with pytest.raises(JobNotFoundError):
            state.delete("missing")

    @pytest.mark.parametrize("backend", BACKENDS, ids=lambda item: item.name)
    def test_reload_new_instance_sees_fields_and_events(
        self,
        tmp_path: Path, backend: StateStoreBackend
    ) -> None:
        first = backend.create(tmp_path)
        first.create(_record(preview=_preview("Day 1"), folder_label="Day1"))
        first.save(
            _record(
                status="done",
                job_type="upload",
                preview=_preview("Day 1"),
                product_url="https://photos.example/a",
                folder_label="Day1",
            )
        )
        first.append_event(
            "job-1",
            JobEvent(
                job_id="job-1",
                stage="done",
                message="https://photos.example/a",
                occurred_at=datetime(2024, 6, 1, 12, 1, tzinfo=timezone.utc),
            ),
        )

        second = backend.create(tmp_path)
        fetched = second.get("job-1")
        assert fetched.status == "done"
        assert fetched.type == "upload"
        assert fetched.product_url == "https://photos.example/a"
        assert fetched.folder_label == "Day1"
        assert fetched.preview is not None
        assert fetched.preview.title == "Day 1"
        events = second.list_events("job-1")
        assert [event.stage for event in events] == ["done"]

    @pytest.mark.parametrize("backend", BACKENDS, ids=lambda item: item.name)
    def test_reload_new_instance_sees_scrape_parent_fields(
        self,
        tmp_path: Path, backend: StateStoreBackend
    ) -> None:
        first = backend.create(tmp_path)
        first.create(
            _record(
                "scrape-1",
                status="done",
                job_type="scrape",
                scrape_url="https://albums.example/day1",
                scrape_headers={"Cookie": "keep-me"},
                folder_label="albums.example",
            )
        )
        first.create(
            _record(
                "preview-1",
                status="done",
                job_type="preview",
                preview=_preview("Day 1"),
                parent_job_id="scrape-1",
            )
        )

        second = backend.create(tmp_path)
        scrape = second.get("scrape-1")
        assert scrape.type == "scrape"
        assert scrape.scrape_url == "https://albums.example/day1"
        assert scrape.scrape_headers == {"Cookie": "keep-me"}
        child = second.get("preview-1")
        assert child.parent_job_id == "scrape-1"
        assert child.preview is not None
        assert child.preview.title == "Day 1"

    def test_json_backend_writes_job_json(self, tmp_path: Path) -> None:
        store = JsonStateStore(tmp_path)
        store.create(_record(folder_label="Day1"))
        assert (tmp_path / "job-1" / JOB_META_NAME).is_file()
        store.append_event("job-1", JobEvent(job_id="job-1", stage="ingest"))
        assert (tmp_path / "job-1" / EVENTS_NAME).is_file()

    def test_json_atomic_write_survives_concurrent_saves(self, tmp_path: Path) -> None:
        """Concurrent savers must not share a fixed ``job.json.tmp`` path."""
        store = JsonStateStore(tmp_path)
        store.create(_record(folder_label="Day1"))
        errors: list[BaseException] = []

        def _save(label: str) -> None:
            try:
                record = store.get("job-1")
                record.folder_label = label
                store.save(record)
            except BaseException as exc:  # noqa: BLE001 — collect any thread failure
                errors.append(exc)

        threads = [
            threading.Thread(target=_save, args=(f"writer-{i}",)) for i in range(24)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == []
        assert store.get("job-1").folder_label.startswith("writer-")
        leftovers = list((tmp_path / "job-1").glob("*.tmp"))
        assert leftovers == []

    def test_json_atomic_tmp_name_includes_xdist_worker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        from src.jobs.persistence import json_state as js

        monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw7")
        monkeypatch.setattr(js.uuid, "uuid4", lambda: type("U", (), {"hex": "abc123"})())
        seen: list[str] = []
        original_replace = Path.replace

        def _capture_replace(self: Path, target: Path) -> Path:  # noqa: ANN001
            seen.append(self.name)
            return original_replace(self, target)

        monkeypatch.setattr(Path, "replace", _capture_replace)
        target = tmp_path / "job.json"
        js._atomic_write_json(target, {"ok": True})
        assert seen == [f"job.json.gw7.{os.getpid()}.abc123.tmp"]
        assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}

    def test_sqlite_backend_does_not_write_job_json(self, tmp_path: Path) -> None:
        store = SqliteStateStore(tmp_path)
        store.create(_record())
        assert (tmp_path / "migrator.sqlite").is_file()
        assert not (tmp_path / "job-1" / JOB_META_NAME).exists()

    def test_sqlite_migrates_legacy_job_json_and_events(self, tmp_path: Path) -> None:
        job_id = "legacy-job"
        root = tmp_path / job_id
        root.mkdir()
        (root / "index.html").write_text("<html></html>", encoding="utf-8")
        meta = {
            "id": job_id,
            "status": "preview_ready",
            "error": None,
            "preview": {
                "title": "Day 1",
                "description": "desc",
                "multi_index": False,
                "journal": None,
                "items": [],
            },
            "product_url": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "folder_label": "Day1",
        }
        (root / JOB_META_NAME).write_text(json.dumps(meta), encoding="utf-8")
        (root / EVENTS_NAME).write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "job_id": job_id,
                            "stage": "ingest",
                            "message": "Writing upload",
                            "current": 0,
                            "total": 2,
                            "extra": None,
                            "occurred_at": "2024-01-01T00:00:01+00:00",
                        },
                        {
                            "job_id": job_id,
                            "stage": "preview_ready",
                            "message": "Day 1",
                            "current": 2,
                            "total": 2,
                            "extra": {"title": "Day 1"},
                            "occurred_at": "2024-01-01T00:00:05+00:00",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

        store = SqliteStateStore(tmp_path)
        record = store.get(job_id)
        assert record.status == "done"
        assert record.type == "preview"
        assert record.number == 1
        assert record.folder_label == "Day1"
        assert record.preview is not None
        assert record.preview.title == "Day 1"
        events = store.list_events(job_id)
        assert [event.stage for event in events] == ["ingest", "preview_ready"]
        assert events[0].kind == "log"
        assert events[0].audience == "ui"
        assert events[1].kind == "lifecycle"
        assert events[1].audience == "ui"
        assert events[1].extra == {"title": "Day 1"}
        assert (root / "index.html").is_file()
        assert (root / JOB_META_NAME).is_file()

    def test_sqlite_migration_does_not_overwrite_existing_sqlite_row(
        self,
        tmp_path: Path,
    ) -> None:
        job_id = "legacy-job"
        root = tmp_path / job_id
        root.mkdir()
        meta = {
            "id": job_id,
            "status": "preview_ready",
            "error": None,
            "preview": None,
            "product_url": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "folder_label": "from-json",
        }
        (root / JOB_META_NAME).write_text(json.dumps(meta), encoding="utf-8")

        first = SqliteStateStore(tmp_path)
        first.save(
            JobRecord(
                id=job_id,
                status="running",
                type="upload",
                preview=None,
                error=None,
                product_url="https://photos.example/a",
                created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                folder_label="from-sqlite",
            )
        )

        second = SqliteStateStore(tmp_path)
        record = second.get(job_id)
        assert record.status == "running"
        assert record.type == "upload"
        assert record.folder_label == "from-sqlite"
        assert record.product_url == "https://photos.example/a"

    def test_sqlite_migrates_legacy_error_status(self, tmp_path: Path) -> None:
        job_id = "legacy-error"
        root = tmp_path / job_id
        root.mkdir()
        (root / JOB_META_NAME).write_text(
            json.dumps(
                {
                    "id": job_id,
                    "status": "error",
                    "error": "parse failed",
                    "preview": None,
                    "product_url": "https://photos.example/a",
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "folder_label": None,
                }
            ),
            encoding="utf-8",
        )

        store = SqliteStateStore(tmp_path)
        record = store.get(job_id)
        assert record.status == "failed"
        assert record.type == "upload"
        assert record.error == "parse failed"

    def test_sqlite_migrates_artifact_only_album_dir(self, tmp_path: Path) -> None:
        job_id = "0d89828b-f9ab-4319-a311-f237b53d0b86"
        root = tmp_path / job_id
        root.mkdir()
        (root / "index.html").write_text(
            '<span class="gallerytitle">2/8/2012 - Day 1</span>',
            encoding="utf-8",
        )
        (root / "hrimages").mkdir()
        (root / "imagepages").mkdir()

        store = SqliteStateStore(tmp_path)
        record = store.get(job_id)
        assert record.status == "done"
        assert record.type == "preview"
        assert record.preview is not None
        assert record.preview.title == "2/8/2012 - Day 1"
        assert record.preview.items == ()

    def test_sqlite_skips_corrupt_job_json_during_migration(self, tmp_path: Path) -> None:
        good = tmp_path / "good-job"
        good.mkdir()
        (good / JOB_META_NAME).write_text(
            json.dumps(
                {
                    "id": "good-job",
                    "status": "done",
                    "type": "preview",
                    "preview": None,
                    "created_at": "2024-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        broken = tmp_path / "broken-json"
        broken.mkdir()
        (broken / JOB_META_NAME).write_text("{not json", encoding="utf-8")

        store = SqliteStateStore(tmp_path)
        ids = {record.id for record in store.list_all()}
        assert ids == {"good-job"}

    def test_import_origin_roundtrip(self, state: StateStore) -> None:
        state.create(_record(import_origin="folder", folder_label="Day1"))
        fetched = state.get("job-1")
        assert fetched.import_origin == "folder"
        state.save(
            _record(
                status="done",
                job_type="preview",
                preview=_preview("Day 1"),
                folder_label="Day1",
                import_origin="web",
            )
        )
        updated = state.get("job-1")
        assert updated.import_origin == "web"
        assert updated.status == "done"

    def test_import_origin_inferred_for_legacy_rows(self, state: StateStore) -> None:
        state.create(_record("folder-job"))
        assert state.get("folder-job").import_origin == "folder"

        state.create(
            _record(
                "scrape-job",
                job_type="scrape",
                scrape_url="https://albums.example/day1",
            )
        )
        assert state.get("scrape-job").import_origin == "web"

        state.create(_record("child-job", parent_job_id="scrape-job"))
        assert state.get("child-job").import_origin == "web"

    def test_json_legacy_meta_without_import_origin_infers(self, tmp_path: Path) -> None:
        job_dir = tmp_path / "legacy-scrape"
        job_dir.mkdir()
        (job_dir / JOB_META_NAME).write_text(
            json.dumps(
                {
                    "id": "legacy-scrape",
                    "status": "done",
                    "type": "scrape",
                    "scrape_url": "https://albums.example/day1",
                    "created_at": "2024-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        store = JsonStateStore(tmp_path)
        record = store.get("legacy-scrape")
        assert record.import_origin == "web"

        folder_dir = tmp_path / "legacy-folder"
        folder_dir.mkdir()
        (folder_dir / JOB_META_NAME).write_text(
            json.dumps(
                {
                    "id": "legacy-folder",
                    "status": "done",
                    "type": "preview",
                    "created_at": "2024-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        assert store.get("legacy-folder").import_origin == "folder"

    def test_sqlite_migrates_legacy_json_without_import_origin(self, tmp_path: Path) -> None:
        folder_id = "legacy-folder"
        web_id = "legacy-web"
        (tmp_path / folder_id).mkdir()
        (tmp_path / folder_id / JOB_META_NAME).write_text(
            json.dumps(
                {
                    "id": folder_id,
                    "status": "done",
                    "type": "preview",
                    "created_at": "2024-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / web_id).mkdir()
        (tmp_path / web_id / JOB_META_NAME).write_text(
            json.dumps(
                {
                    "id": web_id,
                    "status": "done",
                    "type": "preview",
                    "parent_job_id": "scrape-parent",
                    "created_at": "2024-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        store = SqliteStateStore(tmp_path)
        assert store.get(folder_id).import_origin == "folder"
        assert store.get(web_id).import_origin == "web"

