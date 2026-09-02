"""TDD: JobOrchestrator pending/running queues and max concurrent cap."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from src.export.parser import AlbumExportParser
from src.jobs.events import JobEventBus
from src.jobs.orchestrator import (
    DEFAULT_MAX_CONCURRENT,
    INTERRUPTED_ERROR,
    INTERRUPTED_ERROR_CODE,
    JobOrchestrator,
    validate_max_concurrent,
)
from src.jobs.scrape import ScrapeService
from src.jobs.store import JobStore
from src.jobs.workspace import JobWorkspace
from tests.support.fakes.scraper import FakeAlbumScraper, mini_album_files
from tests.support.waits import JobWaiter
from tests.support.suites import OrchestratorSuite

_WAITER = JobWaiter(timeout=3.0)


def _wait_status(store: JobStore, job_id: str, status: str, timeout: float = 3.0) -> None:
    _WAITER.store_status(store, job_id, status, timeout=timeout)


def _wait_snapshot(
    orch: JobOrchestrator,
    key: str,
    *,
    minimum: int = 1,
    timeout: float = 3.0,
) -> None:
    _WAITER.snapshot(orch, key, minimum=minimum, timeout=timeout)




























def job_summary_finished_at_is_none(store: JobStore, job_id: str) -> bool:
    from src.jobs.store import job_summary_to_dict

    return job_summary_to_dict(store.get(job_id))["finished_at"] is None

class TestJobOrchestrator(OrchestratorSuite):
    def test_validate_max_concurrent_bounds(self) -> None:
        assert validate_max_concurrent(2) == 2
        assert validate_max_concurrent("3") == 3
        with pytest.raises(ValueError):
            validate_max_concurrent(0)
        with pytest.raises(ValueError):
            validate_max_concurrent(33)
        with pytest.raises(ValueError):
            validate_max_concurrent("nope")

    def test_cap_one_submit_three_only_one_running(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        orch = JobOrchestrator(store, max_concurrent=1)
        entered = {index: threading.Event() for index in range(3)}
        release = {index: threading.Event() for index in range(3)}
        jobs = [store.create(tmp_path) for _ in range(3)]

        def make_fn(index: int):
            def fn() -> None:
                entered[index].set()
                assert release[index].wait(timeout=5)

            return fn

        for index, job in enumerate(jobs):
            orch.submit(job.id, make_fn(index))

        assert entered[0].wait(timeout=2)
        time.sleep(0.1)
        assert not entered[1].is_set()
        assert not entered[2].is_set()
        assert store.get(jobs[0].id).status == "running"
        assert store.get(jobs[1].id).status == "pending"
        assert store.get(jobs[2].id).status == "pending"
        snap = orch.snapshot()
        assert snap["running"] == 1
        assert snap["pending"] == 2
        assert snap["waiting"] == 0
        assert snap["max_concurrent_jobs"] == 1

        release[0].set()
        assert entered[1].wait(timeout=2)
        time.sleep(0.05)
        assert store.get(jobs[1].id).status == "running"
        assert store.get(jobs[2].id).status == "pending"
        assert not entered[2].is_set()

        release[1].set()
        assert entered[2].wait(timeout=2)
        release[2].set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and orch.snapshot()["running"]:
            time.sleep(0.02)
        assert orch.snapshot()["running"] == 0
        assert orch.snapshot()["pending"] == 0

    def test_raise_max_concurrent_starts_pending(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        orch = JobOrchestrator(store, max_concurrent=1)
        entered = {index: threading.Event() for index in range(3)}
        release = threading.Event()
        jobs = [store.create(tmp_path) for _ in range(3)]

        def make_fn(index: int):
            def fn() -> None:
                entered[index].set()
                assert release.wait(timeout=5)

            return fn

        for index, job in enumerate(jobs):
            orch.submit(job.id, make_fn(index))
        assert entered[0].wait(timeout=2)
        time.sleep(0.05)
        assert not entered[1].is_set()

        orch.set_max_concurrent(3)
        assert entered[1].wait(timeout=2)
        assert entered[2].wait(timeout=2)
        assert orch.snapshot()["running"] == 3
        assert orch.snapshot()["pending"] == 0
        release.set()

    def test_lower_max_concurrent_does_not_kill_running(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        orch = JobOrchestrator(store, max_concurrent=2)
        entered = {index: threading.Event() for index in range(3)}
        release = threading.Event()
        jobs = [store.create(tmp_path) for _ in range(3)]

        def make_fn(index: int):
            def fn() -> None:
                entered[index].set()
                assert release.wait(timeout=5)

            return fn

        for index, job in enumerate(jobs):
            orch.submit(job.id, make_fn(index))
        assert entered[0].wait(timeout=2)
        assert entered[1].wait(timeout=2)
        time.sleep(0.05)
        assert not entered[2].is_set()

        orch.set_max_concurrent(1)
        time.sleep(0.1)
        assert entered[0].is_set()
        assert entered[1].is_set()
        assert not entered[2].is_set()
        assert store.get(jobs[0].id).status == "running"
        assert store.get(jobs[1].id).status == "running"
        assert store.get(jobs[2].id).status == "pending"
        release.set()
        assert entered[2].wait(timeout=2)

    def test_cancel_pending_never_runs(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        orch = JobOrchestrator(store, max_concurrent=1)
        started = threading.Event()
        release = threading.Event()
        ran_second = threading.Event()
        first = store.create(tmp_path)
        second = store.create(tmp_path)

        def first_fn() -> None:
            started.set()
            assert release.wait(timeout=5)

        def second_fn() -> None:
            ran_second.set()

        orch.submit(first.id, first_fn)
        orch.submit(second.id, second_fn)
        assert started.wait(timeout=2)
        store.request_cancel(second.id)
        assert orch.drop(second.id) is True
        release.set()
        time.sleep(0.2)
        assert not ran_second.is_set()
        assert store.get(second.id).status == "cancelled"
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and orch.snapshot()["running"]:
            time.sleep(0.02)
        assert orch.snapshot()["pending"] == 0

    def test_cancel_running_frees_slot(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        orch = JobOrchestrator(store, max_concurrent=1)
        first_started = threading.Event()
        second_started = threading.Event()
        first_release = threading.Event()
        first = store.create(tmp_path)
        second = store.create(tmp_path)

        def first_fn() -> None:
            first_started.set()
            while not store.is_cancelled(first.id):
                if first_release.wait(timeout=0.05):
                    break

        def second_fn() -> None:
            second_started.set()

        orch.submit(first.id, first_fn)
        orch.submit(second.id, second_fn)
        assert first_started.wait(timeout=2)
        store.request_cancel(first.id)
        first_release.set()
        assert second_started.wait(timeout=2)
        assert store.get(second.id).status in {"running", "done"}

    def test_fail_interrupted_running_on_load(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path)
        store.set_status(job.id, "running", job_type="preview")
        pending = store.create(tmp_path)
        orch = JobOrchestrator(store, max_concurrent=2)
        failed = orch.fail_interrupted()
        assert job.id in failed
        assert store.get(job.id).status == "failed"
        assert store.get(job.id).error == INTERRUPTED_ERROR
        assert store.get(job.id).error_code == INTERRUPTED_ERROR_CODE
        assert store.get(pending.id).status == "pending"
        assert orch.snapshot()["running"] == 0

    def test_fail_interrupted_waiting_on_load(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        job = store.create(tmp_path, job_type="scrape")
        store.set_status(job.id, "waiting", job_type="scrape")
        pending = store.create(tmp_path)
        orch = JobOrchestrator(store, max_concurrent=2)
        failed = orch.fail_interrupted()
        assert job.id in failed
        assert store.get(job.id).status == "failed"
        assert store.get(job.id).error == INTERRUPTED_ERROR
        assert store.get(job.id).error_code == INTERRUPTED_ERROR_CODE
        assert store.get(pending.id).status == "pending"
        assert orch.snapshot()["waiting"] == 0

    def test_default_max_concurrent_without_meta(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        orch = JobOrchestrator(store)
        assert DEFAULT_MAX_CONCURRENT == 3
        assert orch.max_concurrent == DEFAULT_MAX_CONCURRENT

    def test_max_concurrent_persists_across_reload(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        orch = JobOrchestrator(store)
        assert orch.max_concurrent == DEFAULT_MAX_CONCURRENT
        orch.set_max_concurrent(5)
        store2 = JobStore.load(tmp_path)
        orch2 = JobOrchestrator(store2)
        assert orch2.max_concurrent == 5

    def test_max_concurrent_persists_sqlite(self, tmp_path: Path) -> None:
        from src.jobs.persistence import build_state_store

        root = tmp_path / "jobs"
        store = JobStore.load(root, state=build_state_store(root))
        orch = JobOrchestrator(store)
        orch.set_max_concurrent(4)
        store2 = JobStore.load(root, state=build_state_store(root))
        orch2 = JobOrchestrator(store2)
        assert orch2.max_concurrent == 4

    def test_hub_children_respect_cap(self, tmp_path: Path) -> None:
        child_urls = [
            f"https://albums.example/hub1/Day{index}/index.html"
            for index in range(1, 9)
        ]
        hold = {url: threading.Event() for url in child_urls}
        started = {url: threading.Event() for url in child_urls}
        fake = FakeAlbumScraper(
            files=(),
            gallery_urls=child_urls,
            by_url={
                url: FakeAlbumScraper(
                    files=mini_album_files(),
                    hold=hold[url],
                    started=started[url],
                )
                for url in child_urls
            },
        )
        store = JobStore.load(tmp_path)
        bus = JobEventBus(persist=store.append_event)
        orch = JobOrchestrator(store, max_concurrent=2)
        service = ScrapeService(
            store=store,
            scraper=fake,
            parser=AlbumExportParser(),
            events=bus,
            workspace=JobWorkspace,
            jobs_root=tmp_path,
            submit=orch.submit,
        )
        parent_id = service.start("https://albums.example/hub1/index.html")
        orch.submit(parent_id, lambda: service.finish(parent_id))
        _wait_status(store, parent_id, "waiting", timeout=5)
        _wait_snapshot(orch, "waiting", minimum=1, timeout=3)
        children = [job for job in store.list_children(parent_id) if job.type == "scrape"]
        assert len(children) == 8
        assert all(job.status in {"pending", "running"} for job in children)
        assert orch.snapshot()["waiting"] >= 1
        assert orch.snapshot()["running"] <= 2

        deadline = time.monotonic() + 3
        running_seen = 0
        while time.monotonic() < deadline:
            live = [job for job in store.list_children(parent_id) if job.type == "scrape"]
            running_seen = max(running_seen, sum(1 for job in live if job.status == "running"))
            if running_seen >= 2:
                break
            time.sleep(0.02)
        assert running_seen == 2
        pending_count = sum(
            1
            for job in store.list_children(parent_id)
            if job.type == "scrape" and job.status == "pending"
        )
        assert pending_count == 6

        for event in hold.values():
            event.set()
        for child in children:
            _wait_status(store, child.id, "done", timeout=8)
        _wait_status(store, parent_id, "done", timeout=5)
        assert store.get(parent_id).status == "done"
        assert not store.get(parent_id).warnings

    def test_waiting_does_not_count_toward_max_concurrent(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        orch = JobOrchestrator(store, max_concurrent=1)
        blocker_started = threading.Event()
        blocker_release = threading.Event()
        extra_started = threading.Event()
        extra_release = threading.Event()
        parent = store.create(tmp_path, job_type="scrape")
        store.create(tmp_path, job_type="scrape", parent_job_id=parent.id)
        blocker = store.create(tmp_path)
        extra = store.create(tmp_path)

        def parent_fn() -> None:
            return None

        def blocker_fn() -> None:
            blocker_started.set()
            assert blocker_release.wait(timeout=5)

        def extra_fn() -> None:
            extra_started.set()
            assert extra_release.wait(timeout=5)

        orch.submit(parent.id, parent_fn)
        _wait_status(store, parent.id, "waiting")
        _wait_snapshot(orch, "waiting", minimum=1)
        snap = orch.snapshot()
        assert snap["waiting"] == 1
        assert snap["running"] == 0
        assert store.get(parent.id).status == "waiting"
        assert job_summary_finished_at_is_none(store, parent.id)

        orch.submit(blocker.id, blocker_fn)
        orch.submit(extra.id, extra_fn)
        assert blocker_started.wait(timeout=2)
        time.sleep(0.05)
        assert not extra_started.is_set()
        snap = orch.snapshot()
        assert snap["running"] == 1
        assert snap["waiting"] == 1
        assert snap["pending"] == 1
        blocker_release.set()
        assert extra_started.wait(timeout=2)
        extra_release.set()

    def test_nested_parent_stays_waiting_while_child_waiting(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        orch = JobOrchestrator(store, max_concurrent=2)
        grand_started = threading.Event()
        grand_release = threading.Event()
        parent = store.create(tmp_path, job_type="scrape")
        child = store.create(tmp_path, job_type="scrape", parent_job_id=parent.id)
        grand = store.create(tmp_path, job_type="preview", parent_job_id=child.id)

        def parent_fn() -> None:
            return None

        def child_fn() -> None:
            return None

        def grand_fn() -> None:
            grand_started.set()
            assert grand_release.wait(timeout=5)

        orch.submit(parent.id, parent_fn)
        orch.submit(child.id, child_fn)
        orch.submit(grand.id, grand_fn)
        assert grand_started.wait(timeout=2)
        _wait_status(store, parent.id, "waiting")
        _wait_status(store, child.id, "waiting")
        _wait_snapshot(orch, "waiting", minimum=2)
        assert store.get(grand.id).status == "running"
        snap = orch.snapshot()
        assert snap["running"] == 1
        assert snap["waiting"] == 2
        grand_release.set()
        _wait_status(store, grand.id, "done")
        _wait_status(store, child.id, "done")
        _wait_status(store, parent.id, "done")

    def test_child_failed_parent_done_with_warnings(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        orch = JobOrchestrator(store, max_concurrent=2)
        parent = store.create(tmp_path, job_type="scrape")
        child = store.create(tmp_path, job_type="scrape", parent_job_id=parent.id)

        def parent_fn() -> None:
            return None

        def child_fn() -> None:
            store.set_status(child.id, "failed", error="site down", job_type="scrape")

        orch.submit(parent.id, parent_fn)
        orch.submit(child.id, child_fn)
        _wait_status(store, child.id, "failed")
        _wait_status(store, parent.id, "done")
        parent_job = store.get(parent.id)
        assert parent_job.status == "done"
        assert parent_job.error is None
        assert parent_job.warnings
        assert any("failed" in warning.lower() for warning in parent_job.warnings)
        assert any(
            str(child.number) in warning or child.id in warning
            for warning in parent_job.warnings
        )
        detail = store.detail_dict(parent.id)
        assert detail["warnings"]
        summary = next(row for row in store.list_summaries() if row["id"] == parent.id)
        assert summary["warnings"]

    def test_parent_own_failure_stays_failed(self, tmp_path: Path) -> None:
        store = JobStore.load(tmp_path)
        orch = JobOrchestrator(store, max_concurrent=1)
        parent = store.create(tmp_path, job_type="scrape")
        store.create(tmp_path, job_type="preview", parent_job_id=parent.id)

        def parent_fn() -> None:
            store.set_status(parent.id, "failed", error="hub down", job_type="scrape")

        orch.submit(parent.id, parent_fn)
        _wait_status(store, parent.id, "failed")
        assert store.get(parent.id).error == "hub down"
        assert store.get(parent.id).status == "failed"

    def test_cancel_waiting_job_cascades(self, tmp_path: Path) -> None:
        from src.jobs.cancel import CancelService
        from src.jobs.events import JobEventBus

        store = JobStore.load(tmp_path)
        orch = JobOrchestrator(store, max_concurrent=1)
        bus = JobEventBus(persist=store.append_event)
        cancel = CancelService(
            store=store,
            events=bus,
            drop_pending=orch.drop,
            on_settled=orch.on_child_settled,
        )
        release = threading.Event()
        parent = store.create(tmp_path, job_type="scrape")
        child = store.create(tmp_path, job_type="scrape", parent_job_id=parent.id)

        def parent_fn() -> None:
            return None

        def child_fn() -> None:
            assert release.wait(timeout=5)

        orch.submit(parent.id, parent_fn)
        orch.submit(child.id, child_fn)
        _wait_status(store, parent.id, "waiting")
        cancel.cancel(parent.id)
        assert store.get(parent.id).status == "cancelled"
        assert store.get(child.id).status == "cancelled"
        assert orch.snapshot()["waiting"] == 0
        release.set()

