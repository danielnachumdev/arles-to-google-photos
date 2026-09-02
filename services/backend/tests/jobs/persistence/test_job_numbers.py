"""TDD: stable autoincrement job numbers (not filtered-table indexes)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.jobs.persistence.json_state import JsonStateStore
from src.jobs.persistence.sqlite_state import SqliteStateStore
from src.jobs.persistence.state import JobRecord
from src.jobs.store import JOB_META_NAME, JobStore, job_summary_to_dict, job_to_dict
from tests.support.builders import JobRecordBuilder
from tests.support.suites import JobStoreSuite


def _record(
    job_id: str,
    *,
    created_at: datetime,
    number: int | None = None,
) -> JobRecord:
    return (
        JobRecordBuilder()
        .with_id(job_id)
        .with_created_at(created_at)
        .with_number(number)
        .build()
    )

class TestJobNumbers(JobStoreSuite):
    def test_job_store_create_assigns_1_2_3(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        first = store.create(tmp_path)
        second = store.create(tmp_path)
        third = store.create(tmp_path, job_type="scrape", scrape_url="https://example.com/a")

        assert first.number == 1
        assert second.number == 2
        assert third.number == 3

    def test_create_upload_from_gets_next_number(self, tmp_path: Path) -> None:
        from src.export.preview import AlbumPreview

        store = JobStore.load(tmp_path)
        preview_job = store.create(tmp_path)
        store.set_preview(
            preview_job.id,
            AlbumPreview(title="Day 1", description=None, multi_index=False, items=()),
        )
        upload = store.create_upload_from(preview_job.id)

        assert preview_job.number == 1
        assert upload.number == 2
        assert upload.number != preview_job.number

    def test_delete_does_not_recycle_numbers(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        first = store.create(tmp_path)
        second = store.create(tmp_path)
        third = store.create(tmp_path)
        store.delete(second.id)
        fourth = store.create(tmp_path)

        assert first.number == 1
        assert third.number == 3
        assert fourth.number == 4
        assert {job.number for job in store.list()} == {1, 3, 4}

    def test_summaries_and_detail_include_number(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        parent = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/day1",
        )
        child = store.create(tmp_path, parent_job_id=parent.id)

        summary = job_summary_to_dict(parent)
        assert summary["number"] == 1
        detail = job_to_dict(parent)
        assert detail["number"] == 1
        listed = {row["id"]: row for row in store.list_summaries()}
        assert listed[parent.id]["number"] == 1
        assert listed[child.id]["number"] == 2
        assert store.detail_dict(parent.id)["number"] == 1
        children = {row["id"]: row for row in store.list_child_summaries(parent.id)}
        assert children[child.id]["number"] == 2

    def test_json_backfill_by_created_at_then_id_and_reload(self, tmp_path: Path) -> None:
        older = tmp_path / "job-b"
        newer = tmp_path / "job-a"
        older.mkdir()
        newer.mkdir()
        (older / JOB_META_NAME).write_text(
            json.dumps(
                {
                    "id": "job-b",
                    "status": "done",
                    "type": "preview",
                    "created_at": "2020-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        (newer / JOB_META_NAME).write_text(
            json.dumps(
                {
                    "id": "job-a",
                    "status": "done",
                    "type": "preview",
                    "created_at": "2024-06-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )

        state = JsonStateStore(tmp_path)
        by_id = {record.id: record for record in state.list_all()}
        assert by_id["job-b"].number == 1
        assert by_id["job-a"].number == 2
        meta_b = json.loads((older / JOB_META_NAME).read_text(encoding="utf-8"))
        meta_a = json.loads((newer / JOB_META_NAME).read_text(encoding="utf-8"))
        assert meta_b["number"] == 1
        assert meta_a["number"] == 2

        store = JobStore.load(tmp_path, state=JsonStateStore(tmp_path))
        assert store.get("job-b").number == 1
        assert store.get("job-a").number == 2
        created = store.create(tmp_path)
        assert created.number == 3

    def test_sqlite_backfill_and_reload(self, tmp_path: Path) -> None:
        first = SqliteStateStore(tmp_path)
        first.create(
            _record(
                "older",
                created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
        )
        first.create(
            _record(
                "newer",
                created_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
            )
        )
        first.close()

        db_path = tmp_path / "migrator.sqlite"
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        conn.execute("UPDATE jobs SET job_number = NULL")
        conn.execute("DELETE FROM meta")
        conn.commit()
        conn.close()

        reopened = SqliteStateStore(tmp_path)
        by_id = {record.id: record for record in reopened.list_all()}
        assert by_id["older"].number == 1
        assert by_id["newer"].number == 2
        reopened.close()

        store = JobStore.load(tmp_path, state=SqliteStateStore(tmp_path))
        assert store.get("older").number == 1
        assert store.get("newer").number == 2
        created = store.create(tmp_path)
        assert created.number == 3

    def test_sqlite_create_assigns_and_survives_reload(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path, state=SqliteStateStore(tmp_path))
        first = store.create(tmp_path)
        second = store.create(tmp_path)
        assert first.number == 1
        assert second.number == 2

        reloaded = JobStore.load(tmp_path, state=SqliteStateStore(tmp_path))
        assert reloaded.get(first.id).number == 1
        assert reloaded.get(second.id).number == 2
        summaries = {row["id"]: row for row in reloaded.list_summaries()}
        assert summaries[first.id]["number"] == 1
        assert summaries[second.id]["number"] == 2
        assert reloaded.detail_dict(first.id)["number"] == 1

