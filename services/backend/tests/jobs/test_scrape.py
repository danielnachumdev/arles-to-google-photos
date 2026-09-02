"""TDD: ScrapeService downloads via Protocol scraper and spawns child jobs."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from src.export.parser import AlbumExportParser
from src.export.scrape.scraper import (
    ArlesGalleryScraper,
    NotArlesGalleryError,
    ScrapeEmptyError,
    ScrapeFetchError,
)
from src.jobs.events import JobEventBus
from src.jobs.scrape import (
    ERROR_FETCH_FAILED,
    ERROR_NOT_ARLES,
    ERROR_SCRAPE_EMPTY,
    ScrapeService,
)
from src.jobs.scraper import wrap_scraper
from src.jobs.store import JobStore
from src.jobs.workspace import JobWorkspace
from tests.support.fakes.http import FakeHttpClient
from tests.support.fakes.scraper import FakeAlbumScraper, mini_album_files
from tests.support.suites import ScrapeServiceSuite


def _service(
    tmp_path: Path,
    *,
    scraper: FakeAlbumScraper | None = None,
    events: JobEventBus | None = None,
) -> tuple[ScrapeService, JobStore, JobEventBus, FakeAlbumScraper]:
    store = JobStore.load(tmp_path)
    bus = events or JobEventBus(persist=store.append_event)
    fake = scraper or FakeAlbumScraper()
    service = ScrapeService(
        store=store,
        scraper=fake,
        parser=AlbumExportParser(),
        events=bus,
        workspace=JobWorkspace,
        jobs_root=tmp_path,
    )
    return service, store, bus, fake

class TestScrapeService(ScrapeServiceSuite):
    def test_scrape_module_exports_service(self) -> None:
        assert ScrapeService is not None

    def test_start_creates_pending_preview_child_before_scrape(
        self,
        tmp_path: Path,
    ) -> None:
        hold = threading.Event()
        started = threading.Event()
        fake = FakeAlbumScraper(hold=hold, started=started)
        service, store, _, _ = _service(tmp_path, scraper=fake)

        job_id = service.start("https://albums.example/day1")

        assert fake.calls == []
        assert not started.is_set()
        parent = store.get(job_id)
        children = store.list_children(job_id)
        assert len(children) == 1
        child = children[0]
        assert child.type == "preview"
        assert child.status == "pending"
        assert child.import_origin == "web"
        assert parent.import_origin == "web"
        assert child.parent_job_id == job_id
        assert child.preview is None
        assert child.folder_label == "albums.example"
        stages = [event.stage for event in parent.events]
        assert "scrape" in stages
        assert "child" in stages
        child_events = [event for event in parent.events if event.stage == "child"]
        assert child_events[0].extra == {"child_id": child.id, "type": "preview"}

        thread = threading.Thread(target=service.finish, args=(job_id,), daemon=True)
        thread.start()
        try:
            assert started.wait(timeout=2)
            blocked = store.get(child.id)
            assert blocked.id == child.id
            assert blocked.status in {"pending", "running"}
            assert blocked.preview is None
        finally:
            hold.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        filled = store.get(child.id)
        assert filled.id == child.id
        assert filled.status == "done"
        assert filled.preview is not None
        assert filled.preview.title == "2/8/2012 - mini fixture"

    def test_preview_child_receives_download_events_during_scrape(
        self,
        tmp_path: Path,
    ) -> None:
        hold = threading.Event()
        started = threading.Event()
        fake = FakeAlbumScraper(hold=hold, started=started)
        service, store, bus, _ = _service(tmp_path, scraper=fake)

        job_id = service.start("https://albums.example/day1")
        preview_id = store.list_children(job_id)[0].id
        child_sub = bus.subscribe(preview_id)

        thread = threading.Thread(target=service.finish, args=(job_id,), daemon=True)
        thread.start()
        try:
            assert started.wait(timeout=2)
            child_during = store.get(preview_id).events
            assert any(event.stage == "scrape" for event in child_during)
            assert any(
                "Fetching gallery index" in event.message for event in child_during
            )
            assert not any(event.stage == "preview_ready" for event in child_during)
            parent_during = store.get(job_id).events
            assert any(
                "Fetching gallery index" in event.message for event in parent_during
            )
            assert not any(event.stage == "preview_ready" for event in parent_during)
            live = []
            while True:
                try:
                    live.append(child_sub.get_nowait())
                except Exception:
                    break
            assert any(event.stage == "scrape" for event in live)
        finally:
            hold.set()
        thread.join(timeout=5)
        assert not thread.is_alive()

        child_after = store.get(preview_id).events
        assert any(event.stage == "scrape" for event in child_after)
        assert any("hrimages/" in event.message or event.message.endswith(".html")
                   or event.message == "index.html" for event in child_after)
        assert any(event.stage == "preview_ready" for event in child_after)
        assert "child" not in [event.stage for event in child_after]
        assert "done" not in [event.stage for event in child_after]
        parent_after = store.get(job_id).events
        assert any(event.stage == "scrape" for event in parent_after)
        assert any(event.stage == "preview_ready" for event in parent_after)
        assert any(event.stage == "done" for event in parent_after)

    def test_child_scrape_job_receives_download_progress(self, tmp_path: Path) -> None:
        child_url = "https://albums.example/day2"
        fake = FakeAlbumScraper(
            files=[("index.html", b"<html>parent</html>", None)],
            gallery_urls=[child_url],
            by_url={child_url: FakeAlbumScraper(files=mini_album_files())},
        )
        service, store, _, _ = _service(tmp_path, scraper=fake)
        parent_id = service.start("https://albums.example/index")
        service.finish(parent_id)

        child_scrape = next(
            job for job in store.list_children(parent_id) if job.type == "scrape"
        )
        scrape_events = store.get(child_scrape.id).events
        assert any(
            "Fetching gallery index" in event.message for event in scrape_events
        )
        assert any(event.stage == "done" for event in scrape_events)
        preview = store.list_children(child_scrape.id)[0]
        preview_events = store.get(preview.id).events
        assert any(
            "Fetching gallery index" in event.message for event in preview_events
        )
        assert any("hrimages/" in event.message or event.message == "index.html"
                   for event in preview_events)
        assert any(event.stage == "preview_ready" for event in preview_events)

    def test_scrape_happy_path_writes_files_and_spawns_preview_child(
        self,
        tmp_path: Path,
    ) -> None:
        service, store, bus, fake = _service(tmp_path)
        job_id = service.start(
            "https://albums.example/day1",
            headers={"Cookie": "secret=1"},
        )
        parent = store.get(job_id)
        assert parent.type == "scrape"
        assert parent.status == "pending"
        assert parent.scrape_url == "https://albums.example/day1"
        assert parent.scrape_headers == {"Cookie": "secret=1"}

        service.finish(job_id)

        parent = store.get(job_id)
        assert parent.status == "done"
        assert parent.type == "scrape"
        assert parent.preview is None
        assert (parent.root / "index.html").is_file()
        assert (parent.root / "hrimages" / "20120802_01hr.JPG").is_file()

        children = store.list_children(job_id)
        assert len(children) == 1
        child = children[0]
        assert child.type == "preview"
        assert child.status == "done"
        assert child.parent_job_id == job_id
        assert child.preview is not None
        assert child.preview.title == "2/8/2012 - mini fixture"
        assert (child.root / "index.html").is_file()
        assert child.root != parent.root

        stages = [event.stage for event in store.get(job_id).events]
        assert "scrape" in stages
        assert "child" in stages
        assert "preview_ready" in stages
        assert "done" in stages
        assert "error" not in stages
        extra_blob = " ".join(
            str(event.extra) for event in store.get(job_id).events if event.extra
        )
        messages = " ".join(event.message for event in store.get(job_id).events)
        assert "secret=1" not in extra_blob
        assert "secret=1" not in messages
        assert fake.calls[0]["url"] == "https://albums.example/day1"
        assert fake.calls[0]["header_names"] == ["Cookie"]

    def test_scrape_gallery_urls_spawn_one_level_of_child_scrapes(
        self,
        tmp_path: Path,
    ) -> None:
        child_url = "https://albums.example/day2"
        fake = FakeAlbumScraper(
            files=mini_album_files(),
            gallery_urls=[child_url],
            by_url={
                child_url: FakeAlbumScraper(
                    files=mini_album_files(),
                    gallery_urls=["https://albums.example/should-not-recurse"],
                )
            },
        )
        service, store, _, _ = _service(tmp_path, scraper=fake)

        parent_id = service.start("https://albums.example/index")
        service.finish(parent_id)

        children = store.list_children(parent_id)
        types = sorted(job.type for job in children)
        assert types == ["preview", "scrape"]
        child_scrape = next(job for job in children if job.type == "scrape")
        assert child_scrape.scrape_url == child_url
        assert child_scrape.parent_job_id == parent_id
        assert child_scrape.status == "done"
        grandchildren = store.list_children(child_scrape.id)
        assert [job.type for job in grandchildren] == ["preview"]
        assert all(
            job.scrape_url != "https://albums.example/should-not-recurse"
            for job in store.list()
        )

    def test_scrape_failure_marks_failed_and_emits_error(self, tmp_path: Path) -> None:
        fake = FakeAlbumScraper(error=RuntimeError("site down"))
        service, store, _, _ = _service(tmp_path, scraper=fake)

        job_id = service.start("https://albums.example/day1")
        with pytest.raises(RuntimeError, match="site down"):
            service.finish(job_id)

        job = store.get(job_id)
        assert job.status == "failed"
        assert job.type == "scrape"
        assert "site down" in (job.error or "")
        assert job.error_code is None
        assert [event.stage for event in job.events][-1] == "error"
        children = store.list_children(job_id)
        assert len(children) == 1
        assert children[0].type == "preview"
        assert children[0].status == "failed"
        assert "site down" in (children[0].error or "")
        assert children[0].preview is None

    def test_unknown_html_scrape_fails_as_not_arles(self, tmp_path: Path) -> None:
        # Plain page: no photo grid, no ≥2 child index links → UNKNOWN (not hub).
        html = (
            b"<!DOCTYPE html><html><head><title>About</title></head>"
            b"<body><h1>About this site</h1>"
            b"<p>No album indexes here.</p>"
            b'<p><a href="https://example.com/help">Help</a></p>'
            b"</body></html>"
        )
        url = "https://albums.example/about.html"
        scraper = wrap_scraper(
            ArlesGalleryScraper(client=FakeHttpClient({url: (200, html)}))
        )
        service, store, _, _ = _service(tmp_path, scraper=scraper)

        job_id = service.start(url)
        original_set_status = store.set_status
        types_when_failed: list[list[str]] = []

        def _set_status(target_id: str, status: str, *args: object, **kwargs: object):
            result = original_set_status(target_id, status, *args, **kwargs)
            if target_id == job_id and status == "failed":
                types_when_failed.append(
                    [child.type for child in store.list_children(target_id)]
                )
            return result

        store.set_status = _set_status  # type: ignore[method-assign]
        with pytest.raises(NotArlesGalleryError):
            service.finish(job_id)

        job = store.get(job_id)
        assert job.status == "failed"
        assert job.error_code == ERROR_NOT_ARLES
        blob = (job.error or "").lower()
        assert "arles" in blob or "unsupported" in blob
        assert job.status != "waiting"
        assert types_when_failed
        assert all("preview" not in types for types in types_when_failed)
        children = store.list_children(job_id)
        assert all(child.type != "preview" for child in children)
        assert all(child.status != "waiting" for child in children)

    def test_fetch_404_scrape_fails_as_fetch_failed(self, tmp_path: Path) -> None:
        url = "https://albums.example/missing/index.html"
        scraper = wrap_scraper(ArlesGalleryScraper(client=FakeHttpClient({})))
        service, store, _, _ = _service(tmp_path, scraper=scraper)

        job_id = service.start(url)
        with pytest.raises(ScrapeFetchError):
            service.finish(job_id)

        job = store.get(job_id)
        assert job.status == "failed"
        assert job.error_code == ERROR_FETCH_FAILED
        assert "404" in (job.error or "")
        assert all(child.type != "preview" for child in store.list_children(job_id))

    def test_fetch_401_scrape_fails_as_fetch_failed(self, tmp_path: Path) -> None:
        url = "https://albums.example/private/index.html"
        scraper = wrap_scraper(
            ArlesGalleryScraper(client=FakeHttpClient({url: (401, b"nope")}))
        )
        service, store, _, _ = _service(tmp_path, scraper=scraper)

        job_id = service.start(url)
        with pytest.raises(ScrapeFetchError):
            service.finish(job_id)

        job = store.get(job_id)
        assert job.status == "failed"
        assert job.error_code == ERROR_FETCH_FAILED
        assert "401" in (job.error or "")

    def test_empty_scrape_result_fails_as_scrape_empty(self, tmp_path: Path) -> None:
        fake = FakeAlbumScraper(error=ScrapeEmptyError(url="https://albums.example/empty"))
        service, store, _, _ = _service(tmp_path, scraper=fake)

        job_id = service.start("https://albums.example/empty")
        with pytest.raises(ScrapeEmptyError):
            service.finish(job_id)

        job = store.get(job_id)
        assert job.status == "failed"
        assert job.error_code == ERROR_SCRAPE_EMPTY
        assert "album" in (job.error or "").lower()
        assert all(child.type != "preview" for child in store.list_children(job_id))

    def test_scrape_rejects_blank_or_non_http_url(self, tmp_path: Path) -> None:
        service, store, _, _ = _service(tmp_path)
        with pytest.raises(ValueError, match="url"):
            service.start("  ")
        with pytest.raises(ValueError, match="url"):
            service.start("ftp://albums.example/day1")
        assert store.list() == []

    def test_load_default_scraper_wraps_arles_gallery_scraper(self) -> None:
        from src.jobs.scraper import UnavailableAlbumScraper, load_default_scraper

        scraper = load_default_scraper()
        assert not isinstance(scraper, UnavailableAlbumScraper)
        assert hasattr(scraper, "scrape")

    def test_dir_scraper_adapter_reads_album_root_and_child_urls(self, tmp_path: Path) -> None:
        from src.export.scrape.models import ScrapeRequest, ScrapeResult as ExportResult
        from src.jobs.scraper import wrap_scraper

        class _Inner:
            def scrape(self, request: ScrapeRequest, output_dir: Path) -> ExportResult:
                dest = Path(output_dir)
                (dest / "index.html").write_text("<html>parent</html>", encoding="utf-8")
                return ExportResult(
                    album_root=dest,
                    child_gallery_urls=("https://albums.example/day2",),
                    gallery_title="Parent",
                )

        adapter = wrap_scraper(_Inner())
        dest = tmp_path / "out"
        result = adapter.scrape(
            "https://albums.example/index",
            headers={"Cookie": "secret=1"},
            output_dir=dest,
        )
        assert [item[0] for item in result.files] == ["index.html"]
        assert result.gallery_urls == ("https://albums.example/day2",)

    def test_parent_index_spawns_child_scrapes_without_preview(self, tmp_path: Path) -> None:
        fake = FakeAlbumScraper(
            files=[("index.html", b"<html>parent</html>", None)],
            gallery_urls=["https://albums.example/day2"],
            by_url={
                "https://albums.example/day2": FakeAlbumScraper(files=mini_album_files())
            },
        )
        service, store, _, _ = _service(tmp_path, scraper=fake)
        parent_id = service.start("https://albums.example/index")
        service.finish(parent_id)

        children = store.list_children(parent_id)
        preview_kids = [job for job in children if job.type == "preview"]
        scrape_kids = [job for job in children if job.type == "scrape"]
        assert preview_kids == []
        assert len(scrape_kids) == 1
        assert scrape_kids[0].scrape_url == "https://albums.example/day2"
        assert scrape_kids[0].status == "done"
        assert store.get(parent_id).status == "done"

    def test_hub_index_spawns_eight_child_scrapes_without_failed_preview(
        self,
        tmp_path: Path,
    ) -> None:
        child_urls = [
            f"https://albums.example/hub1/Day{index}/index.html"
            for index in range(1, 9)
        ]
        fake = FakeAlbumScraper(
            files=(),
            gallery_urls=child_urls,
            by_url={
                url: FakeAlbumScraper(files=mini_album_files()) for url in child_urls
            },
        )
        service, store, _, _ = _service(tmp_path, scraper=fake)
        parent_id = service.start(
            "https://albums.example/hub1/index.html",
            headers={"Cookie": "session=abc"},
        )
        service.finish(parent_id)

        parent = store.get(parent_id)
        assert parent.status == "done"
        children = store.list_children(parent_id)
        assert [job.type for job in children] == ["scrape"] * 8
        assert [job.scrape_url for job in children] == child_urls
        assert all(job.status == "done" for job in children)
        assert all(job.scrape_headers == {"Cookie": "session=abc"} for job in children)
        assert all(job.parent_job_id != parent_id or job.type != "preview" for job in store.list())
        assert [call["url"] for call in fake.calls] == [
            "https://albums.example/hub1/index.html",
            *child_urls,
        ]
        assert all(call["header_names"] == ["Cookie"] for call in fake.calls)

    def test_preview_child_history_includes_progress_and_eta(self, tmp_path: Path) -> None:
        from src.export.scrape.scraper import ArlesGalleryScraper
        from src.jobs.scraper import wrap_scraper
        from tests.export.scrape.test_scraper import (
            FakeClock,
            FakeHttpClient,
            GALLERY_ARL,
            _eta_image_page,
            _eta_index_html,
        )

        base = "https://photos.example/eta-fanout"
        ids = ("pic01", "pic02", "pic03")
        jpeg = b"\xff\xd8" + b"A" * 40_000 + b"\xff\xd9"
        pages = {
            f"{base}/index.html": (200, _eta_index_html(ids).encode("utf-8")),
            f"{base}/Gallery.arl": (200, GALLERY_ARL),
        }
        delays = {}
        for item_id in ids:
            pages[f"{base}/imagepages/{item_id}.html"] = (
                200,
                _eta_image_page(item_id).encode("utf-8"),
            )
            hr_url = f"{base}/hrimages/{item_id}hr.JPG"
            pages[hr_url] = (200, jpeg)
            delays[hr_url] = 1.0
        clock = FakeClock()
        scraper = wrap_scraper(
            ArlesGalleryScraper(
                client=FakeHttpClient(pages, clock=clock, delays=delays),
                monotonic=clock,
            )
        )
        service, store, _, _ = _service(tmp_path, scraper=scraper)

        job_id = service.start(f"{base}/index.html")
        preview_id = store.list_children(job_id)[0].id
        service.finish(job_id)

        preview_events = store.get(preview_id).events
        parent_events = store.get(job_id).events
        preview_saved = [event for event in preview_events if "Saved hrimages/" in event.message]
        parent_saved = [event for event in parent_events if "Saved hrimages/" in event.message]
        assert len(preview_saved) == 3
        assert len(parent_saved) == 3
        assert preview_saved[0].current == 1
        assert preview_saved[0].total == 3
        assert "left" not in preview_saved[0].message
        assert preview_saved[0].extra is not None
        assert "eta_seconds" not in preview_saved[0].extra
        assert "2/3" in preview_saved[1].message
        assert "~1s left" in preview_saved[1].message
        assert preview_saved[1].extra is not None
        assert preview_saved[1].extra.get("eta_seconds") == 1
        assert "~1s left" in parent_saved[1].message
        assert parent_saved[1].extra is not None
        assert parent_saved[1].extra.get("eta_seconds") == 1

    def test_retry_uses_persisted_headers_without_new_job(self, tmp_path: Path) -> None:
        fake = FakeAlbumScraper()
        service, store, _, _ = _service(tmp_path, scraper=fake)
        job_id = service.start(
            "https://albums.example/day1",
            headers={"Authorization": "Bearer tok"},
        )
        service.finish(job_id)
        child_id = store.list_children(job_id)[0].id

        fake.calls.clear()
        service.retry(job_id)

        job = store.get(job_id)
        assert job.id == job_id
        assert job.status == "done"
        assert job.type == "scrape"
        children = store.list_children(job_id)
        assert [c.id for c in children if c.type == "preview"] == [child_id]
        assert fake.calls[0]["header_names"] == ["Authorization"]

