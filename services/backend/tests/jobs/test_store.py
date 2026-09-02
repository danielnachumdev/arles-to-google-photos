"""TDD: JobStore persists job metadata under each job root and reloads from disk."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.export.preview import AlbumPreview, PreviewItem
from src.jobs.events import JobEvent
from src.jobs.store import (
    EVENTS_NAME,
    JOB_META_NAME,
    JobNotArchivableError,
    JobNotFoundError,
    JobStore,
    job_display_title,
    job_summary_to_dict,
    job_to_dict,
    normalize_job_state,
)


from tests.support.builders import PreviewBuilder
from tests.support.suites import JobStoreSuite


def _preview(title: str = "Album") -> AlbumPreview:
    return PreviewBuilder().with_title(title).build()


class _FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)
































































































class TestJobStore(JobStoreSuite):
    def test_create_returns_job_with_id_root_and_pending_preview(self, tmp_path: Path) -> None:
        store = JobStore()
        job = store.create(tmp_path)

        assert isinstance(job.id, str)
        assert job.id
        assert job.root == tmp_path / job.id
        assert job.root.is_dir()
        assert job.status == "pending"
        assert job.type == "preview"
        assert job.import_origin == "folder"
        assert job.number == 1
        assert job.created_at.tzinfo is not None
        assert (job.root / JOB_META_NAME).is_file()

    def test_copy_artifacts_copies_album_files_not_state(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        source = store.create(tmp_path)
        (source.root / "index.html").write_text("<html>hi</html>", encoding="utf-8")
        (source.root / "hrimages").mkdir()
        (source.root / "hrimages" / "a.jpg").write_bytes(b"abc")
        (source.root / EVENTS_NAME).write_text("[]", encoding="utf-8")
        dest = store.create(tmp_path)

        store.copy_artifacts(source.id, dest.id)

        assert (dest.root / "index.html").read_text(encoding="utf-8") == "<html>hi</html>"
        assert (dest.root / "hrimages" / "a.jpg").read_bytes() == b"abc"
        assert not (dest.root / EVENTS_NAME).is_file() or (
            dest.root / EVENTS_NAME
        ).read_text(encoding="utf-8") != "[]"
        assert (source.root / "index.html").read_text(encoding="utf-8") == "<html>hi</html>"

    def test_get_returns_created_job(self, tmp_path: Path) -> None:
        store = JobStore()
        created = store.create(tmp_path)

        fetched = store.get(created.id)

        assert fetched.id == created.id
        assert fetched.root == created.root
        assert fetched.status == "pending"
        assert fetched.type == "preview"

    def test_get_missing_id_raises(self) -> None:
        store = JobStore()
        with pytest.raises(KeyError):
            store.get("missing-job-id")

    def test_set_preview_stores_preview_and_sets_preview_done(self, tmp_path: Path) -> None:
        store = JobStore()
        job = store.create(tmp_path)
        preview = _preview("Day 1")

        updated = store.set_preview(job.id, preview)

        assert updated.status == "done"
        assert updated.type == "preview"
        assert updated.preview is preview
        assert store.get(job.id).status == "done"
        assert store.get(job.id).type == "preview"
        assert store.get(job.id).preview is preview

    def test_set_preview_missing_id_raises(self) -> None:
        store = JobStore()
        with pytest.raises(KeyError):
            store.set_preview("missing-job-id", _preview())

    def test_set_status_updates_status_and_error(self, tmp_path: Path) -> None:
        store = JobStore()
        job = store.create(tmp_path)

        updated = store.set_status(job.id, "running", job_type="preview")
        assert updated.status == "running"
        assert updated.type == "preview"
        assert updated.error is None

        failed = store.set_status(job.id, "failed", error="parse failed", job_type="preview")
        assert failed.status == "failed"
        assert failed.type == "preview"
        assert failed.error == "parse failed"
        assert failed.error_code is None
        assert store.get(job.id).error == "parse failed"

    def test_set_status_persists_error_code(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path, job_type="scrape", scrape_url="https://albums.example/x")
        failed = store.set_status(
            job.id,
            "failed",
            error="Not a supported Arles album: https://albums.example/x",
            error_code="not_arles",
            job_type="scrape",
        )
        assert failed.error_code == "not_arles"
        payload = job_to_dict(failed)
        assert payload["error_code"] == "not_arles"
        assert "supported Arles" in (payload["error"] or "")
        summary = job_summary_to_dict(failed)
        assert summary["error_code"] == "not_arles"
        reloaded = JobStore.load(tmp_path).get(job.id)
        assert reloaded.error_code == "not_arles"
        assert reloaded.error == failed.error

    def test_set_status_missing_id_raises(self) -> None:
        store = JobStore()
        with pytest.raises(KeyError):
            store.set_status("missing-job-id", "failed", error="nope")

    def test_update_preview_replaces_preview_after_edits(self, tmp_path: Path) -> None:
        store = JobStore()
        job = store.create(tmp_path)
        store.set_preview(job.id, _preview("Original"))
        assert store.get(job.id).user_edited is False

        edited = _preview("Edited title")
        updated = store.update_preview(job.id, edited)

        assert updated.preview is edited
        assert updated.preview is not None
        assert updated.preview.title == "Edited title"
        assert updated.status == "done"
        assert updated.type == "preview"
        assert updated.user_edited is True
        assert store.get(job.id).preview is edited
        assert store.get(job.id).user_edited is True
        assert job_to_dict(store.get(job.id))["user_edited"] is True
        assert job_summary_to_dict(store.get(job.id))["user_edited"] is True

        same = store.update_preview(job.id, edited)
        assert same.user_edited is True

        store.set_preview(job.id, _preview("Reparsed"))
        cleared = store.get(job.id)
        assert cleared.preview is not None
        assert cleared.preview.title == "Reparsed"
        assert cleared.user_edited is False

    def test_update_preview_after_done_resets_status_keeps_product_url(
        self,
        tmp_path: Path,
    ) -> None:
        store = JobStore()
        job = store.create(tmp_path)
        store.set_preview(job.id, _preview("Original"))
        store.mark_done(job.id, "https://photos.example/album-1")

        updated = store.update_preview(job.id, _preview("Edited after publish"))

        assert updated.status == "done"
        assert updated.type == "preview"
        assert updated.product_url == "https://photos.example/album-1"
        assert updated.error is None
        assert updated.preview is not None
        assert updated.preview.title == "Edited after publish"

    def test_update_preview_missing_id_raises(self) -> None:
        store = JobStore()
        with pytest.raises(KeyError):
            store.update_preview("missing-job-id", _preview())

    def test_mark_done_sets_status_and_product_url(self, tmp_path: Path) -> None:
        store = JobStore()
        job = store.create(tmp_path)
        store.set_preview(job.id, _preview())

        updated = store.mark_done(job.id, "https://photos.example/album-1")

        assert updated.status == "done"
        assert updated.type == "upload"
        assert updated.product_url == "https://photos.example/album-1"
        assert updated.error is None
        fetched = store.get(job.id)
        assert fetched.status == "done"
        assert fetched.type == "upload"
        assert fetched.product_url == "https://photos.example/album-1"

    def test_mark_done_missing_id_raises(self) -> None:
        store = JobStore()
        with pytest.raises(KeyError):
            store.mark_done("missing-job-id", "https://photos.example/x")

    def test_create_assigns_unique_ids_and_directories(self, tmp_path: Path) -> None:
        store = JobStore()
        first = store.create(tmp_path)
        second = store.create(tmp_path)

        assert first.id != second.id
        assert first.number == 1
        assert second.number == 2
        assert first.root != second.root
        assert first.root.is_dir()
        assert second.root.is_dir()

    def test_preview_and_status_survive_new_store_instance(self, tmp_path: Path) -> None:
        store = JobStore()
        job = store.create(tmp_path, folder_label="Day1")
        store.set_preview(job.id, _preview("Day 1"))
        store.mark_done(job.id, "https://photos.example/album-1")

        reloaded = JobStore.load(tmp_path)
        fetched = reloaded.get(job.id)

        assert fetched.status == "done"
        assert fetched.type == "upload"
        assert fetched.product_url == "https://photos.example/album-1"
        assert fetched.folder_label == "Day1"
        assert fetched.root == job.root
        assert fetched.preview is not None
        assert fetched.preview.title == "Day 1"
        assert fetched.preview.description == "desc"
        assert fetched.preview.journal is not None
        assert fetched.preview.journal.heading == "יומן"
        assert fetched.preview.journal.paragraphs == ("p1", "p2")
        assert len(fetched.preview.items) == 1
        item = fetched.preview.items[0]
        assert item.id == "20120802_01"
        assert item.relpath == "hrimages/20120802_01hr.JPG"
        assert item.caption == "hello"
        assert item.size_bytes == 16
        assert item.taken_on == date(2012, 8, 2)
        assert item.last_modified == datetime(2012, 8, 2, 10, 0, 0)

    def test_load_empty_directory_is_empty_store(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        assert store.list() == []

    def test_load_skips_corrupt_job_dirs(self, tmp_path: Path) -> None:
        store = JobStore()
        good = store.create(tmp_path)
        store.set_preview(good.id, _preview("Keep me"))

        (tmp_path / "not-a-uuid-dir").mkdir()
        broken = tmp_path / "broken-json"
        broken.mkdir()
        (broken / JOB_META_NAME).write_text("{not json", encoding="utf-8")
        empty_meta = tmp_path / "empty-meta"
        empty_meta.mkdir()
        (empty_meta / JOB_META_NAME).write_text("[]", encoding="utf-8")

        reloaded = JobStore.load(tmp_path)
        listed = reloaded.list()
        assert [job.id for job in listed] == [good.id]
        assert reloaded.get(good.id).preview is not None
        assert reloaded.get(good.id).preview.title == "Keep me"

    def test_list_orders_by_created_at_newest_first(self, tmp_path: Path) -> None:
        store = JobStore()
        older = store.create(tmp_path)
        newer = store.create(tmp_path)
        older.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        newer.created_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        store.set_status(older.id, "done", job_type="preview")
        store.set_status(newer.id, "done", job_type="upload")

        assert [job.id for job in store.list()] == [newer.id, older.id]

        reloaded = JobStore.load(tmp_path)
        assert [job.id for job in reloaded.list()] == [newer.id, older.id]

    def test_set_preview_after_done_keeps_product_url(self, tmp_path: Path) -> None:
        store = JobStore()
        job = store.create(tmp_path)
        store.set_preview(job.id, _preview("Original"))
        store.mark_done(job.id, "https://photos.example/album-1")

        updated = store.set_preview(job.id, _preview("Reparsed"))

        assert updated.status == "done"
        assert updated.type == "preview"
        assert updated.product_url == "https://photos.example/album-1"
        assert updated.preview is not None
        assert updated.preview.title == "Reparsed"

    def test_delete_removes_job_from_memory_and_disk(self, tmp_path: Path) -> None:
        store = JobStore()
        keep = store.create(tmp_path)
        drop = store.create(tmp_path)
        (drop.root / "hrimages").mkdir()
        (drop.root / "hrimages" / "a.jpg").write_bytes(b"img")
        store.set_preview(drop.id, _preview("Drop me"))
        drop_root = drop.root
        keep_root = keep.root

        store.delete(drop.id)

        assert not drop_root.exists()
        assert keep_root.is_dir()
        with pytest.raises(JobNotFoundError):
            store.get(drop.id)
        assert store.get(keep.id).id == keep.id
        assert [job.id for job in store.list()] == [keep.id]

    def test_delete_missing_id_raises(self) -> None:
        store = JobStore()
        with pytest.raises(JobNotFoundError):
            store.delete("missing-job-id")

    def test_delete_does_not_resurrect_on_load(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path, folder_label="Day1")
        store.set_preview(job.id, _preview("Gone"))
        store.delete(job.id)

        reloaded = JobStore.load(tmp_path)
        with pytest.raises(JobNotFoundError):
            reloaded.get(job.id)
        assert reloaded.list() == []

    def test_delete_ignores_tampered_root_and_only_removes_store_job_dir(
        self,
        tmp_path: Path,
    ) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        outside = tmp_path.parent / f"outside-{job.id}"
        outside.mkdir()
        marker = outside / "keep.txt"
        marker.write_text("safe", encoding="utf-8")
        job.root = outside

        store.delete(job.id)

        assert marker.is_file()
        assert not (tmp_path / job.id).exists()
        with pytest.raises(JobNotFoundError):
            store.get(job.id)

    def test_delete_does_not_remove_store_base_when_root_tampered(
        self,
        tmp_path: Path,
    ) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        job_dir = tmp_path / job.id
        job.root = tmp_path

        store.delete(job.id)

        assert tmp_path.is_dir()
        assert not job_dir.exists()
        with pytest.raises(JobNotFoundError):
            store.get(job.id)

    def test_find_by_title_returns_none_when_missing(self, tmp_path: Path) -> None:
        store = JobStore()
        job = store.create(tmp_path)
        store.set_preview(job.id, _preview("Day 1"))

        assert store.find_by_title("Day 2") is None
        assert store.find_by_title("   ") is None
        assert store.find_by_title("") is None

    def test_find_by_title_matches_normalized_whitespace(self, tmp_path: Path) -> None:
        store = JobStore()
        job = store.create(tmp_path)
        store.set_preview(job.id, _preview("  Day 1 "))

        found = store.find_by_title("Day 1")
        assert found is not None
        assert found.id == job.id
        assert store.find_by_title("\tDay 1\n").id == job.id

    def test_find_by_title_prefers_preview_over_upload(self, tmp_path: Path) -> None:
        store = JobStore()
        preview_job = store.create(tmp_path)
        store.set_preview(preview_job.id, _preview("Day 1"))
        upload = store.create_upload_from(preview_job.id)
        store.mark_done(upload.id, "https://photos.example/album-1")

        found = store.find_by_title("Day 1")
        assert found is not None
        assert found.id == preview_job.id
        assert found.type == "preview"

    def test_find_by_title_without_url_picks_newest(self, tmp_path: Path) -> None:
        store = JobStore()
        older = store.create(tmp_path)
        newer = store.create(tmp_path)
        older.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        newer.created_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        store.set_preview(older.id, _preview("Day 1"))
        store.set_preview(newer.id, _preview("Day 1"))
        store.set_status(older.id, "done", job_type="preview")
        store.set_status(newer.id, "done", job_type="preview")

        found = store.find_by_title("Day 1")
        assert found is not None
        assert found.id == newer.id

    def test_list_returns_preview_and_upload_runs(self, tmp_path: Path) -> None:
        store = JobStore()
        preview_job = store.create(tmp_path)
        store.set_preview(preview_job.id, _preview("Day 1"))
        upload = store.create_upload_from(preview_job.id)
        store.mark_done(upload.id, "https://photos.example/album-1")

        listed = store.list()
        assert {job.id for job in listed} == {preview_job.id, upload.id}

    def test_list_albums_dedupes_same_title_prefers_preview(self, tmp_path: Path) -> None:
        store = JobStore()
        preview_job = store.create(tmp_path)
        store.set_preview(preview_job.id, _preview("Day 1"))
        upload = store.create_upload_from(preview_job.id)
        store.mark_done(upload.id, "https://photos.example/album-1")

        albums = store.list_albums()
        assert [job.id for job in albums] == [preview_job.id]
        summaries = store.list_album_summaries()
        assert [row["id"] for row in summaries] == [preview_job.id]
        assert summaries[0]["product_url"] == "https://photos.example/album-1"

    def test_list_albums_dedupes_same_title_prefers_newest_without_url(
        self,
        tmp_path: Path,
    ) -> None:
        store = JobStore()
        older = store.create(tmp_path)
        newer = store.create(tmp_path)
        older.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        newer.created_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        store.set_preview(older.id, _preview("Day 1"))
        store.set_preview(newer.id, _preview("Day 1"))
        store.set_status(older.id, "done", job_type="preview")
        store.set_status(newer.id, "done", job_type="preview")

        listed = store.list_albums()
        assert [job.id for job in listed] == [newer.id]

    def test_list_same_title_tie_breaks_by_stable_id(self, tmp_path: Path) -> None:
        store = JobStore()
        first = store.create(tmp_path)
        second = store.create(tmp_path)
        stamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
        first.created_at = stamp
        second.created_at = stamp
        store.set_preview(first.id, _preview("Same"))
        store.set_preview(second.id, _preview("Same"))

        winner_id = max(first.id, second.id)
        assert [job.id for job in store.list_albums()] == [winner_id]
        found = store.find_by_title("Same")
        assert found is not None
        assert found.id == winner_id

    def test_list_keeps_distinct_album_titles(self, tmp_path: Path) -> None:
        store = JobStore()
        first = store.create(tmp_path)
        second = store.create(tmp_path)
        store.set_preview(first.id, _preview("Album A"))
        store.set_preview(second.id, _preview("Album B"))

        assert {job.id for job in store.list()} == {first.id, second.id}

    def test_list_does_not_collapse_jobs_without_title(self, tmp_path: Path) -> None:
        store = JobStore()
        first = store.create(tmp_path)
        second = store.create(tmp_path)

        assert {job.id for job in store.list()} == {first.id, second.id}

    def test_append_event_persists_and_reloads(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        occurred = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        event = JobEvent(
            job_id=job.id,
            stage="ingest",
            message="Writing upload",
            current=0,
            total=2,
            extra={"items": 1},
            occurred_at=occurred,
        )

        store.append_event(job.id, event)

        assert (job.root / EVENTS_NAME).is_file()
        assert len(store.get(job.id).events) == 1
        reloaded = JobStore.load(tmp_path)
        events = reloaded.get(job.id).events
        assert len(events) == 1
        assert events[0].stage == "ingest"
        assert events[0].message == "Writing upload"
        assert events[0].current == 0
        assert events[0].total == 2
        assert events[0].extra == {"items": 1}
        assert events[0].occurred_at == occurred

    def test_append_event_appends_in_order(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        store.append_event(job.id, JobEvent(job_id=job.id, stage="ingest", message="a"))
        store.append_event(job.id, JobEvent(job_id=job.id, stage="parse", message="b"))
        store.append_event(
            job.id, JobEvent(job_id=job.id, stage="preview_ready", message="c")
        )

        stages = [event.stage for event in store.get(job.id).events]
        assert stages == ["ingest", "parse", "preview_ready"]
        reloaded = JobStore.load(tmp_path)
        assert [event.stage for event in reloaded.get(job.id).events] == stages

    def test_append_event_missing_id_raises(self) -> None:
        store = JobStore()
        with pytest.raises(JobNotFoundError):
            store.append_event("missing", JobEvent(job_id="missing", stage="error"))

    def test_load_skips_corrupt_events_file(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        (job.root / EVENTS_NAME).write_text("{not json", encoding="utf-8")

        reloaded = JobStore.load(tmp_path)
        assert reloaded.get(job.id).events == []

    def test_job_to_dict_does_not_include_events(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        store.append_event(job.id, JobEvent(job_id=job.id, stage="ingest"))
        payload = job_to_dict(store.get(job.id))
        assert "events" not in payload
        assert payload["type"] == "preview"
        assert payload["status"] == "pending"
        assert payload["number"] == 1
        assert payload["finished_at"] is None
        assert payload["updated_at"]

    def test_job_summary_includes_timing_fields(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        start = job.created_at
        store.append_event(
            job.id,
            JobEvent(
                job_id=job.id,
                stage="ingest",
                message="Writing upload",
                occurred_at=start + timedelta(seconds=2),
            ),
        )
        store.set_status(job.id, "running", job_type="preview")

        running = job_summary_to_dict(store.get(job.id))
        assert running["status"] == "running"
        assert running["type"] == "preview"
        assert running["number"] == 1
        assert running["updated_at"] == (start + timedelta(seconds=2)).isoformat()
        assert running["finished_at"] is None
        assert running["duration_seconds"] is not None
        assert running["duration_seconds"] >= 0
        assert running["started_at"]
        assert running["running_started_at"]
        assert running["last_stage"] == "ingest"
        assert running["preview_job_id"] is None

        store.set_preview(job.id, _preview("Day 1"))
        store.append_event(
            job.id,
            JobEvent(
                job_id=job.id,
                stage="preview_ready",
                message="Day 1",
                occurred_at=start + timedelta(seconds=12),
            ),
        )

        ready = job_summary_to_dict(store.get(job.id))
        assert ready["status"] == "done"
        assert ready["type"] == "preview"
        assert ready["title"] == "Day 1"
        assert ready["item_count"] == 1
        assert ready["updated_at"] == (start + timedelta(seconds=12)).isoformat()
        assert ready["finished_at"] == ready["updated_at"]
        assert ready["duration_seconds"] is not None
        assert ready["duration_seconds"] >= 0
        assert ready["started_at"] == running["started_at"]
        assert ready["running_started_at"] is None
        assert ready["last_stage"] == "preview_ready"
        assert ready["preview_job_id"] is None

        detail_ready = store.detail_dict(job.id)
        assert detail_ready["finished_at"] == ready["finished_at"]
        assert detail_ready["updated_at"] == ready["updated_at"]
        assert detail_ready["duration_seconds"] == ready["duration_seconds"]
        assert detail_ready["started_at"] == ready["started_at"]
        assert detail_ready["running_started_at"] is None

    def test_terminal_job_summaries_include_finished_at(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        failed = store.create(tmp_path)
        start = failed.created_at
        store.set_status(failed.id, "failed", error="parse failed", job_type="preview")
        store.append_event(
            failed.id,
            JobEvent(
                job_id=failed.id,
                stage="failed",
                message="parse failed",
                occurred_at=start + timedelta(seconds=4),
            ),
        )
        failed_summary = job_summary_to_dict(store.get(failed.id))
        assert failed_summary["status"] == "failed"
        assert failed_summary["finished_at"] == (start + timedelta(seconds=4)).isoformat()
        assert store.detail_dict(failed.id)["finished_at"] == failed_summary["finished_at"]

        cancelled = store.create(tmp_path)
        store.set_status(cancelled.id, "cancelled")
        cancelled_summary = job_summary_to_dict(store.get(cancelled.id))
        assert cancelled_summary["status"] == "cancelled"
        assert cancelled_summary["finished_at"] == cancelled.created_at.isoformat()
        assert store.detail_dict(cancelled.id)["finished_at"] == cancelled_summary["finished_at"]

        running = store.create(tmp_path)
        store.set_status(running.id, "running", job_type="preview")
        running_summary = job_summary_to_dict(store.get(running.id))
        assert running_summary["finished_at"] is None
        assert store.detail_dict(running.id)["finished_at"] is None

        waiting = store.create(tmp_path, job_type="scrape")
        store.set_status(waiting.id, "waiting", job_type="scrape")
        waiting_summary = job_summary_to_dict(store.get(waiting.id))
        assert waiting_summary["status"] == "waiting"
        assert waiting_summary["finished_at"] is None
        assert store.detail_dict(waiting.id)["finished_at"] is None
        assert waiting_summary["warnings"] == []
        assert store.detail_dict(waiting.id)["warnings"] == []

    def test_duration_excludes_pending_queue_time(self, tmp_path: Path) -> None:
        clock = _FakeClock(datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc))
        with patch("src.jobs.store._utc_now", clock):
            store = JobStore.load(tmp_path)
            job = store.create(tmp_path)
            clock.advance(30)
            pending = job_summary_to_dict(store.get(job.id))
            assert pending["status"] == "pending"
            assert pending["duration_seconds"] is None
            assert pending["started_at"] is None

            store.set_status(job.id, "running", job_type="preview")
            started = store.get(job.id).started_at
            assert started == datetime(2026, 8, 8, 10, 0, 30, tzinfo=timezone.utc)
            clock.advance(5)
            running = job_summary_to_dict(store.get(job.id))
            assert running["duration_seconds"] == 5
            assert running["started_at"] == started.isoformat()
            assert running["running_started_at"] == started.isoformat()

            clock.advance(7)
            store.set_status(job.id, "done", job_type="preview")
            done = job_summary_to_dict(store.get(job.id))
            assert done["duration_seconds"] == 12
            assert done["started_at"] == started.isoformat()
            assert done["running_started_at"] is None
            assert store.detail_dict(job.id)["duration_seconds"] == 12

    def test_duration_is_zero_when_cancelled_while_pending(self, tmp_path: Path) -> None:
        clock = _FakeClock(datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc))
        with patch("src.jobs.store._utc_now", clock):
            store = JobStore.load(tmp_path)
            job = store.create(tmp_path)
            clock.advance(90)
            store.set_status(job.id, "cancelled")
            summary = job_summary_to_dict(store.get(job.id))
            assert summary["status"] == "cancelled"
            assert summary["duration_seconds"] == 0
            assert summary["started_at"] is None
            assert summary["running_started_at"] is None
            assert store.detail_dict(job.id)["duration_seconds"] == 0

    def test_duration_excludes_waiting_time(self, tmp_path: Path) -> None:
        clock = _FakeClock(datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc))
        with patch("src.jobs.store._utc_now", clock):
            store = JobStore.load(tmp_path)
            job = store.create(tmp_path, job_type="scrape")
            clock.advance(20)
            store.set_status(job.id, "running", job_type="scrape")
            clock.advance(10)
            store.set_status(job.id, "waiting", job_type="scrape")
            clock.advance(60)
            waiting = job_summary_to_dict(store.get(job.id))
            assert waiting["status"] == "waiting"
            assert waiting["duration_seconds"] == 10
            assert waiting["running_started_at"] is None
            assert waiting["started_at"]

            store.set_status(job.id, "done", job_type="scrape")
            done = job_summary_to_dict(store.get(job.id))
            assert done["duration_seconds"] == 10

    def test_duration_accumulates_multiple_running_intervals(self, tmp_path: Path) -> None:
        clock = _FakeClock(datetime(2026, 8, 8, 13, 0, tzinfo=timezone.utc))
        with patch("src.jobs.store._utc_now", clock):
            store = JobStore.load(tmp_path)
            job = store.create(tmp_path, job_type="scrape")
            store.set_status(job.id, "running", job_type="scrape")
            clock.advance(4)
            store.set_status(job.id, "waiting", job_type="scrape")
            clock.advance(50)
            store.set_status(job.id, "running", job_type="scrape")
            clock.advance(6)
            store.set_status(job.id, "done", job_type="scrape")
            assert job_summary_to_dict(store.get(job.id))["duration_seconds"] == 10

    def test_started_at_persists_across_store_reload(self, tmp_path: Path) -> None:
        clock = _FakeClock(datetime(2026, 8, 8, 14, 0, tzinfo=timezone.utc))
        with patch("src.jobs.store._utc_now", clock):
            store = JobStore.load(tmp_path)
            job = store.create(tmp_path)
            clock.advance(3)
            store.set_status(job.id, "running", job_type="preview")
            started = store.get(job.id).started_at
            running_started = store.get(job.id).running_started_at
            assert started == datetime(2026, 8, 8, 14, 0, 3, tzinfo=timezone.utc)
            assert running_started == started
            assert store.get(job.id).run_seconds == 0.0

        reloaded = JobStore.load(tmp_path)
        fetched = reloaded.get(job.id)
        assert fetched.started_at == started
        assert fetched.running_started_at == running_started
        assert fetched.run_seconds == 0.0
        summary = job_summary_to_dict(fetched)
        assert summary["started_at"] == started.isoformat()
        assert summary["running_started_at"] == running_started.isoformat()

    def test_warnings_roundtrip_in_detail_and_summary(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path, job_type="scrape")
        store.set_status(
            job.id,
            "done",
            job_type="scrape",
            warnings=["Child #12 failed: site down"],
        )
        fetched = store.get(job.id)
        assert fetched.warnings == ["Child #12 failed: site down"]
        assert job_summary_to_dict(fetched)["warnings"] == ["Child #12 failed: site down"]
        assert store.detail_dict(job.id)["warnings"] == ["Child #12 failed: site down"]

    def test_request_cancel_waiting_job(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path, job_type="scrape")
        store.set_status(job.id, "waiting", job_type="scrape")
        child = store.create(tmp_path, job_type="preview", parent_job_id=job.id)
        ids = store.request_cancel(job.id)
        assert job.id in ids
        assert child.id in ids
        assert store.get(job.id).status == "cancelled"
        assert store.get(child.id).status == "cancelled"

    def test_create_upload_from_shares_artifact_root_and_isolates_state(
        self,
        tmp_path: Path,
    ) -> None:
        store = JobStore.load(tmp_path)
        preview_job = store.create(tmp_path, folder_label="Day1")
        store.set_preview(preview_job.id, _preview("Day 1"))
        store.append_event(
            preview_job.id,
            JobEvent(job_id=preview_job.id, stage="preview_ready", message="Day 1"),
        )
        (preview_job.root / "hrimages").mkdir()
        marker = preview_job.root / "hrimages" / "20120802_01hr.JPG"
        marker.write_bytes(b"\xff\xd8\xff\xd9")

        upload = store.create_upload_from(preview_job.id)

        assert upload.id != preview_job.id
        assert upload.number == 2
        assert preview_job.number == 1
        assert upload.type == "upload"
        assert upload.status == "pending"
        assert upload.source_job_id == preview_job.id
        assert upload.root == preview_job.root
        assert upload.folder_label == "Day1"
        assert upload.product_url is None
        assert upload.events == []
        assert upload.preview is not None
        assert upload.preview.title == "Day 1"
        assert marker.is_file()
        assert not (tmp_path / upload.id / "hrimages").exists()

        store.append_event(
            upload.id, JobEvent(job_id=upload.id, stage="publish", message="Starting")
        )
        source = store.get(preview_job.id)
        assert [event.stage for event in source.events] == ["preview_ready"]
        assert [event.stage for event in store.get(upload.id).events] == ["publish"]

        reloaded = JobStore.load(tmp_path)
        fetched = reloaded.get(upload.id)
        assert fetched.root == preview_job.root
        assert fetched.source_job_id == preview_job.id
        assert fetched.preview is not None
        assert fetched.preview.title == "Day 1"
        assert [event.stage for event in fetched.events] == ["publish"]
        assert [event.stage for event in reloaded.get(preview_job.id).events] == [
            "preview_ready"
        ]

    def test_delete_preview_cascades_upload_jobs_not_sibling_albums(
        self,
        tmp_path: Path,
    ) -> None:
        store = JobStore.load(tmp_path)
        preview_job = store.create(tmp_path)
        store.set_preview(preview_job.id, _preview("Day 1"))
        (preview_job.root / "index.html").write_text("<html></html>", encoding="utf-8")
        upload = store.create_upload_from(preview_job.id)
        other = store.create(tmp_path)
        store.set_preview(other.id, _preview("Day 2"))
        preview_root = preview_job.root

        store.delete(preview_job.id)

        with pytest.raises(JobNotFoundError):
            store.get(preview_job.id)
        with pytest.raises(JobNotFoundError):
            store.get(upload.id)
        assert store.get(other.id).id == other.id
        assert not preview_root.exists()

    def test_delete_upload_does_not_remove_preview_artifacts(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        preview_job = store.create(tmp_path)
        store.set_preview(preview_job.id, _preview("Day 1"))
        marker = preview_job.root / "index.html"
        marker.write_text("<html></html>", encoding="utf-8")
        upload = store.create_upload_from(preview_job.id)

        store.delete(upload.id)

        with pytest.raises(JobNotFoundError):
            store.get(upload.id)
        assert store.get(preview_job.id).type == "preview"
        assert marker.is_file()

    def test_delete_duplicates_for_title_keeps_winner(self, tmp_path: Path) -> None:
        store = JobStore()
        keep = store.create(tmp_path)
        extra = store.create(tmp_path)
        other = store.create(tmp_path)
        store.set_preview(keep.id, _preview("Day 1"))
        store.set_preview(extra.id, _preview("Day 1"))
        store.set_preview(other.id, _preview("Day 2"))
        extra_root = extra.root

        store.delete_duplicates_for_title("Day 1", keep_id=keep.id)

        assert store.get(keep.id).id == keep.id
        with pytest.raises(KeyError):
            store.get(extra.id)
        assert not extra_root.exists()
        assert store.get(other.id).preview is not None
        assert store.get(other.id).preview.title == "Day 2"

    @pytest.mark.parametrize(
        "raw_status, raw_type, product_url, expected_status, expected_type",
        [
            ("created", None, None, "pending", "preview"),
            ("ingesting", None, None, "running", "preview"),
            ("preview_ready", None, None, "done", "preview"),
            ("publishing", None, None, "running", "upload"),
            ("done", None, "https://photos.example/a", "done", "upload"),
            ("done", None, None, "done", "preview"),
            ("error", None, None, "failed", "preview"),
            ("error", None, "https://photos.example/a", "failed", "upload"),
            ("pending", None, None, "pending", "preview"),
            ("running", "upload", None, "running", "upload"),
            ("failed", None, "https://photos.example/a", "failed", "upload"),
            ("done", "preview", "https://photos.example/a", "done", "preview"),
            ("pending", "scrape", None, "pending", "scrape"),
            ("running", "scrape", None, "running", "scrape"),
            ("done", "scrape", None, "done", "scrape"),
            ("failed", "scrape", None, "failed", "scrape"),
            ("cancelled", "scrape", None, "cancelled", "scrape"),
            ("cancelled", "preview", None, "cancelled", "preview"),
            ("waiting", "scrape", None, "waiting", "scrape"),
            ("waiting", None, None, "waiting", "preview"),
            (None, None, None, "pending", "preview"),
            ("unknown", None, None, "pending", "preview"),
        ],
    )
    def test_normalize_job_state_maps_legacy_and_missing(
        self,
        raw_status: str | None,
        raw_type: str | None,
        product_url: str | None,
        expected_status: str,
        expected_type: str,
    ) -> None:
        assert normalize_job_state(raw_status, raw_type, product_url) == (
            expected_status,
            expected_type,
        )

    def test_job_store_sqlite_roundtrip_without_job_json(self, tmp_path: Path) -> None:
        from src.jobs.persistence import FsArtifactStore, SqliteStateStore

        store = JobStore.load(
            tmp_path,
            state=SqliteStateStore(tmp_path),
            artifacts=FsArtifactStore(tmp_path),
        )
        job = store.create(tmp_path, folder_label="Day1")
        store.set_preview(job.id, _preview("Day 1"))
        store.append_event(
            job.id,
            JobEvent(job_id=job.id, stage="preview_ready", message="Day 1"),
        )
        assert not (job.root / JOB_META_NAME).exists()

        reloaded = JobStore.load(
            tmp_path,
            state=SqliteStateStore(tmp_path),
            artifacts=FsArtifactStore(tmp_path),
        )
        fetched = reloaded.get(job.id)
        assert fetched.status == "done"
        assert fetched.type == "preview"
        assert fetched.folder_label == "Day1"
        assert fetched.root == job.root
        assert fetched.preview is not None
        assert fetched.preview.title == "Day 1"
        assert [event.stage for event in fetched.events] == ["preview_ready"]

    def test_load_migrates_legacy_job_json_statuses(self, tmp_path: Path) -> None:
        import json

        cases = [
            ("legacy-created", "created", None, None, "pending", "preview"),
            ("legacy-ingesting", "ingesting", None, None, "running", "preview"),
            ("legacy-preview", "preview_ready", None, None, "done", "preview"),
            ("legacy-publishing", "publishing", None, None, "running", "upload"),
            (
                "legacy-done-url",
                "done",
                None,
                "https://photos.example/a",
                "done",
                "upload",
            ),
            ("legacy-done-no-url", "done", None, None, "done", "preview"),
            ("legacy-error", "error", None, None, "failed", "preview"),
            (
                "legacy-error-url",
                "error",
                None,
                "https://photos.example/a",
                "failed",
                "upload",
            ),
        ]
        for job_id, status, job_type, product_url, _, _ in cases:
            root = tmp_path / job_id
            root.mkdir()
            meta = {
                "id": job_id,
                "status": status,
                "error": None,
                "preview": None,
                "product_url": product_url,
                "created_at": "2024-01-01T00:00:00+00:00",
                "folder_label": job_id,
            }
            if job_type is not None:
                meta["type"] = job_type
            (root / JOB_META_NAME).write_text(
                json.dumps(meta), encoding="utf-8"
            )

        store = JobStore.load(tmp_path)
        for job_id, _, _, _, expected_status, expected_type in cases:
            job = store.get(job_id)
            assert job.status == expected_status, job_id
            assert job.type == expected_type, job_id

    def test_create_scrape_job_persists_url_headers_and_parent(
        self,
        tmp_path: Path,
    ) -> None:
        store = JobStore.load(tmp_path)
        parent = store.create(
            tmp_path,
            job_type="scrape",
            folder_label="albums.example",
            scrape_url="https://albums.example/day1",
            scrape_headers={"Cookie": "secret=1", "Authorization": "Bearer x"},
        )
        child = store.create(
            tmp_path,
            job_type="preview",
            parent_job_id=parent.id,
            folder_label="Day1",
        )

        assert parent.type == "scrape"
        assert parent.status == "pending"
        assert parent.scrape_url == "https://albums.example/day1"
        assert parent.scrape_headers == {
            "Cookie": "secret=1",
            "Authorization": "Bearer x",
        }
        assert parent.parent_job_id is None
        assert child.parent_job_id == parent.id
        assert child.type == "preview"

        children = store.list_children(parent.id)
        assert [job.id for job in children] == [child.id]

        payload = job_to_dict(parent, child_ids=[c.id for c in children], preview_job_id=child.id)
        assert payload["type"] == "scrape"
        assert payload["scrape_url"] == "https://albums.example/day1"
        assert payload["parent_job_id"] is None
        assert payload["child_ids"] == [child.id]
        assert payload["preview_job_id"] == child.id
        assert payload["has_headers"] is True
        assert payload["header_names"] == ["Cookie", "Authorization"]
        assert "secret=1" not in str(payload)
        assert "Bearer x" not in str(payload)
        assert "scrape_headers" not in payload

        summary = job_summary_to_dict(parent, preview_job_id=child.id)
        assert summary["type"] == "scrape"
        assert summary["title"] is None
        assert summary["scrape_url"] == "https://albums.example/day1"
        assert job_display_title(parent) is None
        assert summary["parent_job_id"] is None
        assert summary["preview_job_id"] == child.id
        assert "secret=1" not in str(summary)

        listed = {row["id"]: row for row in store.list_summaries()}
        assert listed[parent.id]["preview_job_id"] == child.id
        assert listed[child.id]["preview_job_id"] is None
        assert store.detail_dict(parent.id)["preview_job_id"] == child.id

        reloaded = JobStore.load(tmp_path)
        fetched = reloaded.get(parent.id)
        assert fetched.type == "scrape"
        assert fetched.scrape_headers == {
            "Cookie": "secret=1",
            "Authorization": "Bearer x",
        }
        assert [job.id for job in reloaded.list_children(parent.id)] == [child.id]

    def test_list_includes_scrape_runs_library_excludes_scrape_only(
        self,
        tmp_path: Path,
    ) -> None:
        store = JobStore.load(tmp_path)
        first = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/day1",
        )
        second = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/day1",
        )
        other = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/day2",
        )
        first.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        second.created_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        other.created_at = datetime(2024, 7, 1, tzinfo=timezone.utc)
        store.set_status(first.id, "done", job_type="scrape")
        store.set_status(second.id, "done", job_type="scrape")
        store.set_status(other.id, "done", job_type="scrape")

        listed = store.list()
        assert {job.id for job in listed} == {first.id, second.id, other.id}
        assert store.list_albums() == []
        assert store.list_album_summaries() == []

    def test_list_albums_uses_preview_child_not_scrape_parent(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        scrape = store.create(
            tmp_path,
            job_type="scrape",
            folder_label="albums.example",
            scrape_url="https://albums.example/day1",
        )
        preview = store.create(
            tmp_path,
            job_type="preview",
            parent_job_id=scrape.id,
            folder_label="albums.example",
        )
        orphan = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/day2",
        )
        scrape.created_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        preview.created_at = datetime(2024, 6, 1, 0, 0, 1, tzinfo=timezone.utc)
        orphan.created_at = datetime(2024, 7, 1, tzinfo=timezone.utc)
        store.set_preview(preview.id, _preview("Day 1"))
        store.set_status(scrape.id, "done", job_type="scrape")
        store.set_status(orphan.id, "done", job_type="scrape")

        listed = store.list()
        assert {job.id for job in listed} == {scrape.id, preview.id, orphan.id}

        albums = store.list_albums()
        assert [job.id for job in albums] == [preview.id]
        summaries = store.list_album_summaries()
        assert [row["id"] for row in summaries] == [preview.id]
        assert summaries[0]["type"] == "preview"
        assert summaries[0]["title"] == "Day 1"

    def test_delete_scrape_cascades_children_not_siblings(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        parent = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/day1",
        )
        (parent.root / "index.html").write_text("<html></html>", encoding="utf-8")
        preview = store.create(tmp_path, parent_job_id=parent.id)
        store.set_preview(preview.id, _preview("Day 1"))
        grandchild_upload = store.create_upload_from(preview.id)
        sibling = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/day2",
        )
        parent_root = parent.root
        preview_root = preview.root

        store.delete(parent.id)

        with pytest.raises(JobNotFoundError):
            store.get(parent.id)
        with pytest.raises(JobNotFoundError):
            store.get(preview.id)
        with pytest.raises(JobNotFoundError):
            store.get(grandchild_upload.id)
        assert store.get(sibling.id).id == sibling.id
        assert not parent_root.exists()
        assert not preview_root.exists()

    def test_job_store_sqlite_roundtrip_scrape_fields(self, tmp_path: Path) -> None:
        from src.jobs.persistence import FsArtifactStore, SqliteStateStore

        store = JobStore.load(
            tmp_path,
            state=SqliteStateStore(tmp_path),
            artifacts=FsArtifactStore(tmp_path),
        )
        parent = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/day1",
            scrape_headers={"Cookie": "sqlite-secret"},
            folder_label="albums.example",
        )
        child = store.create(tmp_path, parent_job_id=parent.id)
        store.set_preview(child.id, _preview("Day 1"))

        reloaded = JobStore.load(
            tmp_path,
            state=SqliteStateStore(tmp_path),
            artifacts=FsArtifactStore(tmp_path),
        )
        fetched = reloaded.get(parent.id)
        assert fetched.type == "scrape"
        assert fetched.scrape_url == "https://albums.example/day1"
        assert fetched.scrape_headers == {"Cookie": "sqlite-secret"}
        kids = reloaded.list_children(parent.id)
        assert [job.id for job in kids] == [child.id]
        assert kids[0].preview is not None
        assert kids[0].preview.title == "Day 1"
        summaries = {row["id"]: row for row in reloaded.list_summaries()}
        assert summaries[parent.id]["preview_job_id"] == child.id
        assert summaries[child.id]["preview_job_id"] is None
        assert summaries[parent.id]["number"] == 1
        assert summaries[child.id]["number"] == 2
        assert reloaded.detail_dict(parent.id)["preview_job_id"] == child.id
        assert reloaded.detail_dict(parent.id)["number"] == 1
        assert reloaded.get(parent.id).number == 1
        assert reloaded.get(child.id).number == 2
        assert reloaded.get(parent.id).import_origin == "web"
        assert reloaded.get(child.id).import_origin == "web"
        assert reloaded.detail_dict(parent.id)["import_origin"] == "web"
        assert reloaded.detail_dict(child.id)["import_origin"] == "web"
        assert summaries[parent.id]["import_origin"] == "web"
        assert summaries[child.id]["import_origin"] == "web"

    def test_create_upload_from_optional_parent_job_id_roundtrip(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        preview_job = store.create(tmp_path, auto_publish=True, folder_label="Day1")
        store.set_preview(preview_job.id, _preview("Day 1"))

        orphan = store.create_upload_from(preview_job.id)
        assert orphan.parent_job_id is None
        assert orphan.source_job_id == preview_job.id
        assert store.list_children(preview_job.id) == []

        upload = store.create_upload_from(preview_job.id, parent_job_id=preview_job.id)
        assert upload.parent_job_id == preview_job.id
        assert upload.source_job_id == preview_job.id
        assert upload.auto_publish is False
        children = store.list_children(preview_job.id)
        assert [job.id for job in children] == [upload.id]

        detail = store.detail_dict(preview_job.id)
        assert detail["auto_publish"] is True
        assert detail["child_ids"] == [upload.id]
        summary = job_summary_to_dict(store.get(preview_job.id))
        assert summary["auto_publish"] is True

        reloaded = JobStore.load(tmp_path)
        assert reloaded.get(preview_job.id).auto_publish is True
        assert reloaded.get(upload.id).parent_job_id == preview_job.id
        assert reloaded.get(orphan.id).parent_job_id is None
        assert [job.id for job in reloaded.list_children(preview_job.id)] == [upload.id]

    def test_create_sets_import_origin_folder_and_web(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        folder = store.create(tmp_path)
        assert folder.import_origin == "folder"
        assert store.detail_dict(folder.id)["import_origin"] == "folder"
        assert job_summary_to_dict(folder)["import_origin"] == "folder"

        scrape = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/day1",
        )
        assert scrape.import_origin == "web"
        child = store.create(tmp_path, parent_job_id=scrape.id)
        assert child.import_origin == "web"
        assert child.type == "preview"
        assert store.detail_dict(child.id)["import_origin"] == "web"
        assert job_summary_to_dict(child)["import_origin"] == "web"

        reloaded = JobStore.load(tmp_path)
        assert reloaded.get(folder.id).import_origin == "folder"
        assert reloaded.get(scrape.id).import_origin == "web"
        assert reloaded.get(child.id).import_origin == "web"

    def test_create_upload_from_copies_import_origin(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        web_preview = store.create(
            tmp_path, parent_job_id="scrape-1", import_origin="web"
        )
        store.set_preview(web_preview.id, _preview("Day 1"))
        web_upload = store.create_upload_from(web_preview.id)
        assert web_upload.import_origin == "web"

        folder_preview = store.create(tmp_path)
        store.set_preview(folder_preview.id, _preview("Day 2"))
        folder_upload = store.create_upload_from(folder_preview.id)
        assert folder_upload.import_origin == "folder"

        reloaded = JobStore.load(tmp_path)
        assert reloaded.get(web_upload.id).import_origin == "web"
        assert reloaded.get(folder_upload.id).import_origin == "folder"

    def test_archive_hides_from_list_keeps_get_and_artifacts(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path, folder_label="Day1")
        store.set_preview(job.id, _preview("Day 1"))
        (job.root / "index.html").write_text("<html>keep</html>", encoding="utf-8")

        archived_ids = store.archive(job.id)

        assert archived_ids == [job.id]
        fetched = store.get(job.id)
        assert fetched.archived_at is not None
        assert fetched.status == "done"
        assert fetched.preview is not None
        assert fetched.preview.title == "Day 1"
        assert (job.root / "index.html").is_file()
        assert [row["id"] for row in store.list_summaries()] == []
        assert store.list() == []
        included = store.list(include_archived=True)
        assert [row.id for row in included] == [job.id]
        summary = job_summary_to_dict(fetched)
        assert summary["archived_at"] == fetched.archived_at.isoformat()
        detail = store.detail_dict(job.id)
        assert detail["archived_at"] == fetched.archived_at.isoformat()

        reloaded = JobStore.load(tmp_path)
        assert reloaded.get(job.id).archived_at is not None
        assert reloaded.list() == []
        assert (job.root / "index.html").is_file()

    def test_archive_keeps_album_in_deduped_list(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        store.set_preview(job.id, _preview("Day 1"))
        assert [row["id"] for row in store.list_album_summaries()] == [job.id]

        store.archive(job.id)

        assert [job.id for job in store.list()] == []
        albums = store.list_albums()
        assert [row.id for row in albums] == [job.id]
        summaries = store.list_album_summaries()
        assert [row["id"] for row in summaries] == [job.id]
        assert summaries[0]["title"] == "Day 1"
        assert summaries[0]["archived_at"]
        assert store.find_by_title("Day 1") is None

    def test_archive_older_run_keeps_newer_album_pointer(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        older = store.create(tmp_path)
        newer = store.create(tmp_path)
        older.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        newer.created_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        store.set_preview(older.id, _preview("Day 1"))
        store.set_preview(newer.id, _preview("Day 1"))
        store.set_status(older.id, "done", job_type="preview")
        store.set_status(newer.id, "done", job_type="preview")

        store.archive(older.id)

        assert [row.id for row in store.list()] == [newer.id]
        albums = store.list_album_summaries()
        assert [row["id"] for row in albums] == [newer.id]
        assert albums[0]["archived_at"] is None
        assert store.find_by_title("Day 1").id == newer.id

    def test_archive_keeps_product_url_from_archived_upload(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        preview = store.create(tmp_path)
        store.set_preview(preview.id, _preview("Day 1"))
        upload = store.create_upload_from(preview.id)
        store.mark_done(upload.id, "https://photos.example/album-1")

        store.archive(upload.id)

        summaries = store.list_album_summaries()
        assert [row["id"] for row in summaries] == [preview.id]
        assert summaries[0]["product_url"] == "https://photos.example/album-1"

    def test_archive_forbidden_on_active_job(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        pending = store.create(tmp_path)
        running = store.create(tmp_path)
        waiting = store.create(tmp_path, job_type="scrape")
        store.set_status(running.id, "running", job_type="preview")
        store.set_status(waiting.id, "waiting", job_type="scrape")

        with pytest.raises(JobNotArchivableError):
            store.archive(pending.id)
        with pytest.raises(JobNotArchivableError):
            store.archive(running.id)
        with pytest.raises(JobNotArchivableError):
            store.archive(waiting.id)
        assert pending.archived_at is None
        assert store.get(running.id).archived_at is None
        assert {job.id for job in store.list()} == {
            pending.id,
            running.id,
            waiting.id,
        }

    def test_archive_cascades_descendants_and_rejects_active_child(
        self, tmp_path: Path
    ) -> None:
        store = JobStore.load(tmp_path)
        hub = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/hub",
        )
        child = store.create(
            tmp_path,
            job_type="scrape",
            parent_job_id=hub.id,
            scrape_url="https://albums.example/day1",
        )
        preview = store.create(tmp_path, parent_job_id=child.id)
        store.set_preview(preview.id, _preview("Day 1"))
        store.set_status(hub.id, "done", job_type="scrape")
        store.set_status(child.id, "done", job_type="scrape")
        sibling = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/other",
        )
        store.set_status(sibling.id, "done", job_type="scrape")

        archived_ids = store.archive(hub.id)

        assert set(archived_ids) == {hub.id, child.id, preview.id}
        assert store.get(hub.id).archived_at is not None
        assert store.get(child.id).archived_at is not None
        assert store.get(preview.id).archived_at is not None
        assert store.get(sibling.id).archived_at is None
        listed = {job.id for job in store.list()}
        assert listed == {sibling.id}
        assert [row.id for row in store.list_albums()] == [preview.id]
        assert store.find_by_title("Day 1") is None

        active_hub = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/hub2",
        )
        active_child = store.create(
            tmp_path,
            job_type="scrape",
            parent_job_id=active_hub.id,
            scrape_url="https://albums.example/day2",
        )
        store.set_status(active_hub.id, "done", job_type="scrape")
        store.set_status(active_child.id, "running", job_type="scrape")
        with pytest.raises(JobNotArchivableError):
            store.archive(active_hub.id)
        assert store.get(active_hub.id).archived_at is None
        assert store.get(active_child.id).archived_at is None

    def test_archive_is_idempotent(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        store.set_preview(job.id, _preview("Day 1"))
        first = store.archive(job.id)
        stamp = store.get(job.id).archived_at
        second = store.archive(job.id)
        assert first == [job.id]
        assert second == [job.id]
        assert store.get(job.id).archived_at == stamp

    def test_archive_missing_id_raises(self) -> None:
        store = JobStore()
        with pytest.raises(JobNotFoundError):
            store.archive("missing-job-id")

