"""Small SRP units: job numbers, cancel ensure, ingest peek title, events, restart."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.jobs.cancel import CancelService, store_is_cancelled
from src.jobs.events import JobEventBus, event_from_dict, infer_event_kind
from src.jobs.ingest import peek_gallery_title
from src.jobs.persistence.job_numbers import (
    parse_job_number,
    read_seq_file,
    write_seq_file,
)
from src.jobs.restart import JobNotRestartableError, RestartService
from src.jobs.store import JobStore
from tests.support.builders import PreviewBuilder, PreviewItemBuilder
from tests.support.suites import JobStoreSuite

class TestJobHelpers(JobStoreSuite):
    def test_parse_job_number_rejects_bool_and_non_positive(self) -> None:
        assert parse_job_number(None) is None
        assert parse_job_number(True) is None
        assert parse_job_number("nope") is None
        assert parse_job_number(0) is None
        assert parse_job_number(-2) is None
        assert parse_job_number("3") == 3

    def test_read_seq_file_variants(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.json"
        assert read_seq_file(missing) == 1
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert read_seq_file(bad) == 1
        value_key = tmp_path / "value.json"
        value_key.write_text(json.dumps({"value": 7}), encoding="utf-8")
        assert read_seq_file(value_key) == 7
        bare = tmp_path / "bare.json"
        bare.write_text("4", encoding="utf-8")
        assert read_seq_file(bare) == 4
        write_seq_file(tmp_path / "seq.json", 9)
        assert read_seq_file(tmp_path / "seq.json") == 9

    def test_store_is_cancelled_without_checker(self) -> None:
        assert store_is_cancelled(object(), "job-1") is False

    def test_cancel_if_running_noop_for_missing_and_terminal(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        assert store.cancel_if_running("missing") is False
        job = store.create(tmp_path)
        store.set_status(job.id, "done", job_type="preview")
        assert store.cancel_if_running(job.id) is False
        running = store.create(tmp_path)
        store.set_status(running.id, "running", job_type="preview")
        assert store.cancel_if_running(running.id) is True
        assert store.get(running.id).status == "cancelled"

    def test_ensure_cancelled_marks_running_parent_and_child(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        parent = store.create(
            tmp_path, job_type="scrape", scrape_url="https://albums.example/a"
        )
        child = store.create(tmp_path, parent_job_id=parent.id)
        store.set_status(parent.id, "running", job_type="scrape")
        store.set_status(child.id, "running", job_type="preview")
        bus = JobEventBus(persist=store.append_event)
        newly = CancelService(store, bus).ensure_cancelled(parent.id, "scrape")
        assert parent.id in newly
        assert child.id in newly
        assert store.get(parent.id).status == "cancelled"
        assert store.get(child.id).status == "cancelled"

    def test_ensure_cancelled_idempotent_when_already_cancelled(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        store.set_status(job.id, "cancelled", job_type="preview")
        newly = CancelService(store, JobEventBus()).ensure_cancelled(job.id, "preview")
        assert newly == []

    def test_peek_gallery_title_variants(self) -> None:
        assert peek_gallery_title([("readme.txt", b"hi", None)]) is None
        assert (
            peek_gallery_title(
                [("index.html", b"<html><body>no title</body></html>", None)]
            )
            is None
        )
        assert (
            peek_gallery_title(
                [
                    (
                        "index.html",
                        '<span class="gallerytitle">  Day 1\xa0 </span>'.encode("utf-8"),
                        None,
                    )
                ]
            )
            == "Day 1"
        )
        broken = b"\xff<span class=\"gallerytitle\">Day</span>"
        assert peek_gallery_title([("index.html", broken, None)]) == "Day"

    def test_event_kind_alias_and_naive_timestamp(self) -> None:
        assert infer_event_kind("ingest", "progress") == "lifecycle"
        event = event_from_dict(
            {
                "stage": "ingest",
                "occurred_at": "2024-01-01T12:00:00",
                "kind": "log",
            },
            default_job_id="job-1",
        )
        assert event.job_id == "job-1"
        assert event.occurred_at.tzinfo is not None

    def test_event_bus_persist_keyerror_is_ignored(self) -> None:
        def boom(_job_id: str, _event: object) -> None:
            raise KeyError("gone")

        bus = JobEventBus(persist=boom)
        event = bus.emit("job-1", "ingest", "ok")
        assert event.stage == "ingest"

    def test_restart_service_rejects_non_cancelled_and_bad_mode(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        service = RestartService(
            store=store,
            scrape=MagicMock(),
            reprocess=MagicMock(),
            publish=MagicMock(),
            jobs_root=tmp_path,
            submit=MagicMock(),
        )
        with pytest.raises(JobNotRestartableError):
            service.preview(job.id)
        with pytest.raises(JobNotRestartableError):
            service.restart(job.id)
        store.set_status(job.id, "cancelled", job_type="preview")
        with pytest.raises(ValueError, match="unsupported restart mode"):
            service.restart(job.id, mode="nope")

    def test_restart_upload_requires_token(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        preview = store.create(tmp_path)
        store.set_preview(
            preview.id,
            PreviewBuilder()
            .with_title("Day")
            .no_journal()
            .with_items(PreviewItemBuilder().with_size(1).with_last_modified(None).with_taken_on(None).build())
            .build(),
        )
        upload = store.create_upload_from(preview.id)
        store.set_status(upload.id, "cancelled", job_type="upload")
        service = RestartService(
            store=store,
            scrape=MagicMock(),
            reprocess=MagicMock(),
            publish=MagicMock(),
            jobs_root=tmp_path,
            submit=MagicMock(),
        )
        with pytest.raises(ValueError, match="access token"):
            service.restart(upload.id)

    def test_restart_scrape_remaining_when_all_done_raises(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        hub = store.create(
            tmp_path, job_type="scrape", scrape_url="https://albums.example/hub"
        )
        child = store.create(
            tmp_path,
            job_type="scrape",
            scrape_url="https://albums.example/day1",
            parent_job_id=hub.id,
        )
        store.set_status(hub.id, "cancelled", job_type="scrape")
        store.set_status(child.id, "done", job_type="scrape")
        service = RestartService(
            store=store,
            scrape=MagicMock(),
            reprocess=MagicMock(),
            publish=MagicMock(),
            jobs_root=tmp_path,
            submit=MagicMock(),
        )
        with pytest.raises(ValueError, match="no remaining"):
            service.restart(hub.id, mode="remaining")

    def test_restart_scrape_missing_url_raises(self, tmp_path: Path) -> None:
        store = MagicMock()
        job = MagicMock()
        job.status = "cancelled"
        job.type = "scrape"
        job.scrape_url = None
        store.get.return_value = job
        service = RestartService(
            store=store,
            scrape=MagicMock(),
            reprocess=MagicMock(),
            publish=MagicMock(),
            jobs_root=tmp_path,
            submit=MagicMock(),
        )
        with pytest.raises(ValueError, match="scrape url missing"):
            service.restart("scrape-1")

