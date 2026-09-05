"""TDD: PublishService creates a new upload job and leaves the preview alone."""
from __future__ import annotations

from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import pytest

from src.export.preview import AlbumPreview, PreviewItem
from tests.support.builders import PreviewBuilder, PreviewItemBuilder
from src.jobs.store import JobNotFoundError
from tests.support.suites import MockJobServiceSuite


def _preview(*items: PreviewItem, title: str = "Mini") -> AlbumPreview:
    if not items:
        items = (
            PreviewItemBuilder()
            .with_caption("hello")
            .with_size(4)
            .with_last_modified(None)
            .with_taken_on(None)
            .build(),
        )
    return PreviewBuilder().with_title(title).no_journal().with_items(*items).build()


def _job(
    tmp_path: Path,
    preview: AlbumPreview | None = None,
    *,
    job_id: str = "job-1",
    status: str = "done",
    job_type: str = "preview",
) -> MagicMock:
    job = MagicMock()
    job.id = job_id
    job.root = tmp_path / "jobs" / "job-1"
    job.status = status if preview is not None else "pending"
    job.type = job_type
    job.preview = preview
    job.error = None
    job.product_url = None
    job.source_job_id = None
    return job


def _service(store: MagicMock, publisher: MagicMock, events: MagicMock, gp_factory: MagicMock):
    from src.jobs.publish import PublishService

    return PublishService(
        store=store,
        publisher=publisher,
        events=events,
        gp_factory=gp_factory,
    )


def _emit_stages(events: MagicMock) -> List[str]:
    return [call.args[1] for call in events.emit.call_args_list]


def _store_for(source: MagicMock, upload: MagicMock) -> MagicMock:
    store = MagicMock()
    jobs = {source.id: source, upload.id: upload}

    def get_job(job_id: str) -> MagicMock:
        try:
            return jobs[job_id]
        except KeyError as exc:
            raise JobNotFoundError(job_id) from exc

    def ensure_local_root(job_id: str) -> Path:
        return get_job(job_id).root

    store.get.side_effect = get_job
    store.ensure_local_root.side_effect = ensure_local_root
    store.create_upload_from.return_value = upload
    return store

class TestPublishService(MockJobServiceSuite):
    def test_publish_module_exports_service(self) -> None:
        from src.jobs.publish import PublishService

        assert PublishService is not None

    def test_publish_happy_path_creates_upload_job_and_emits_done(self, tmp_path: Path) -> None:
        preview = _preview()
        source = _job(tmp_path, preview)
        upload = _job(tmp_path, preview, job_id="upload-1", job_type="upload", status="pending")
        store = _store_for(source, upload)

        album = MagicMock()
        album.productUrl = "https://photos.example/album-1"
        publisher = MagicMock()
        publisher.publish.return_value = album

        events = MagicMock()
        gp = MagicMock(name="GooglePhotos")
        gp_factory = MagicMock(return_value=gp)

        upload_id = _service(store, publisher, events, gp_factory).publish(
            "job-1", access_token="ya29.tok"
        )

        assert upload_id == "upload-1"
        store.create_upload_from.assert_called_once_with("job-1")
        store.set_status.assert_any_call("upload-1", "running", job_type="upload")
        store.mark_done.assert_called_once_with("upload-1", "https://photos.example/album-1")
        assert all(call.args[0] != "job-1" for call in store.set_status.call_args_list)
        assert all(call.args[0] != "job-1" for call in store.mark_done.call_args_list)
        gp_factory.assert_called_once_with("ya29.tok")
        publisher.publish.assert_called_once()
        pub_args, pub_kwargs = publisher.publish.call_args
        assert pub_args[0] is gp
        assert pub_args[1] == upload.root
        assert pub_args[2] is preview
        sink = pub_kwargs.get("sink")
        if sink is None and len(pub_args) > 3:
            sink = pub_args[3]
        assert sink is not None
        assert callable(getattr(sink, "emit", None))

        stages = _emit_stages(events)
        assert "done" in stages
        assert "error" not in stages
        done_calls = [c for c in events.emit.call_args_list if c.args[1] == "done"]
        assert done_calls
        assert done_calls[0].args[0] == "upload-1"
        extra = done_calls[0].kwargs.get("extra") or {}
        assert extra.get("product_url") == "https://photos.example/album-1"

    def test_publish_missing_job_raises(self, tmp_path: Path) -> None:
        store = MagicMock()
        store.get.side_effect = JobNotFoundError("missing")
        with pytest.raises(JobNotFoundError):
            _service(store, MagicMock(), MagicMock(), MagicMock()).publish(
                "missing", access_token="ya29.tok"
            )
        store.create_upload_from.assert_not_called()

    def test_publish_without_preview_raises_value_error(self, tmp_path: Path) -> None:
        job = _job(tmp_path, preview=None)
        store = MagicMock()
        store.get.return_value = job
        publisher = MagicMock()
        events = MagicMock()

        with pytest.raises(ValueError, match="preview not ready"):
            _service(store, publisher, events, MagicMock()).publish(
                "job-1", access_token="ya29.tok"
            )

        publisher.publish.assert_not_called()
        store.create_upload_from.assert_not_called()
        store.mark_done.assert_not_called()

    def test_publish_empty_items_raises_without_calling_photos(self, tmp_path: Path) -> None:
        preview = AlbumPreview(
            title="Mini",
            description="desc",
            multi_index=False,
            items=(),
        )
        job = _job(tmp_path, preview)
        store = MagicMock()
        store.get.return_value = job
        publisher = MagicMock()
        gp_factory = MagicMock()

        with pytest.raises(ValueError, match="no items to publish"):
            _service(store, publisher, MagicMock(), gp_factory).publish(
                "job-1", access_token="ya29.tok"
            )

        gp_factory.assert_not_called()
        publisher.publish.assert_not_called()
        store.create_upload_from.assert_not_called()

    def test_publish_already_done_upload_creates_another_job(self, tmp_path: Path) -> None:
        preview = _preview()
        source = _job(
            tmp_path, preview, job_id="upload-old", job_type="upload", status="done"
        )
        source.product_url = "https://photos.example/album-1"
        upload = _job(
            tmp_path, preview, job_id="upload-new", job_type="upload", status="pending"
        )
        store = _store_for(source, upload)

        album = MagicMock()
        album.productUrl = "https://photos.example/album-2"
        publisher = MagicMock()
        publisher.publish.return_value = album
        gp_factory = MagicMock(return_value=MagicMock())

        upload_id = _service(store, publisher, MagicMock(), gp_factory).publish(
            "upload-old", access_token="ya29.tok"
        )

        assert upload_id == "upload-new"
        store.create_upload_from.assert_called_once_with("upload-old")
        store.set_status.assert_any_call("upload-new", "running", job_type="upload")
        store.mark_done.assert_called_once_with("upload-new", "https://photos.example/album-2")
        publisher.publish.assert_called_once()

    def test_publish_already_running_raises(self, tmp_path: Path) -> None:
        job = _job(tmp_path, _preview(), job_type="upload", status="running")
        store = MagicMock()
        store.get.return_value = job
        publisher = MagicMock()

        with pytest.raises(ValueError, match="publish already in progress"):
            _service(store, publisher, MagicMock(), MagicMock()).publish(
                "job-1", access_token="ya29.tok"
            )

        publisher.publish.assert_not_called()
        store.create_upload_from.assert_not_called()

    def test_publish_failure_sets_error_on_upload_job_emits_and_reraises(
        self,
        tmp_path: Path,
    ) -> None:
        preview = _preview()
        source = _job(tmp_path, preview)
        upload = _job(tmp_path, preview, job_id="upload-1", job_type="upload", status="pending")
        store = _store_for(source, upload)
        publisher = MagicMock()
        publisher.publish.side_effect = RuntimeError("oauth failed")
        events = MagicMock()
        gp_factory = MagicMock(return_value=MagicMock())

        with pytest.raises(RuntimeError, match="oauth failed"):
            _service(store, publisher, events, gp_factory).publish(
                "job-1", access_token="ya29.tok"
            )

        store.mark_done.assert_not_called()
        store.set_status.assert_any_call(
            "upload-1", "failed", error="oauth failed", job_type="upload"
        )
        stages = _emit_stages(events)
        assert "error" in stages
        assert "done" not in stages
        error_calls = [c for c in events.emit.call_args_list if c.args[1] == "error"]
        assert error_calls
        assert error_calls[0].args[0] == "upload-1"
        assert "oauth failed" in error_calls[0].args[2]

    def test_publish_http_error_not_framed_as_local_read(self, tmp_path: Path) -> None:
        from requests import HTTPError, Response

        from src.jobs.publish import _format_publish_failure

        response = Response()
        response.status_code = 400
        response.url = "https://photoslibrary.googleapis.com/v1/uploads"
        exc = HTTPError(
            "400 Client Error: Bad Request for url: "
            "https://photoslibrary.googleapis.com/v1/uploads",
            response=response,
        )
        message = _format_publish_failure(exc)
        assert "Google Photos API error" in message
        assert "Could not read a photo" not in message
        assert "photoslibrary.googleapis.com" in message

    def test_start_with_parent_emits_child_and_passes_parent_id(self, tmp_path: Path) -> None:
        preview = _preview()
        source = _job(tmp_path, preview)
        upload = _job(tmp_path, preview, job_id="upload-1", job_type="upload", status="pending")
        store = _store_for(source, upload)
        events = MagicMock()

        upload_id = _service(store, MagicMock(), events, MagicMock()).start(
            "job-1", access_token="ya29.tok", parent_job_id="job-1"
        )

        assert upload_id == "upload-1"
        store.create_upload_from.assert_called_once_with("job-1", parent_job_id="job-1")
        child_calls = [c for c in events.emit.call_args_list if c.args[1] == "child"]
        assert child_calls
        assert child_calls[0].args[0] == "job-1"
        assert child_calls[0].args[2] == "upload-1"
        extra = child_calls[0].kwargs.get("extra") or {}
        assert extra.get("child_id") == "upload-1"
        assert extra.get("type") == "upload"

    def test_start_leaves_upload_pending_without_calling_publisher(self, tmp_path: Path) -> None:
        preview = _preview()
        source = _job(tmp_path, preview)
        upload = _job(tmp_path, preview, job_id="upload-1", job_type="upload", status="pending")
        store = _store_for(source, upload)
        publisher = MagicMock()
        gp_factory = MagicMock()

        upload_id = _service(store, publisher, MagicMock(), gp_factory).start(
            "job-1", access_token="ya29.tok"
        )

        assert upload_id == "upload-1"
        store.create_upload_from.assert_called_once_with("job-1")
        running_calls = [
            call
            for call in store.set_status.call_args_list
            if len(call.args) > 1 and call.args[1] == "running"
        ]
        assert running_calls == []
        publisher.publish.assert_not_called()
        gp_factory.assert_not_called()
        store.mark_done.assert_not_called()

    def test_finish_runs_publisher_after_start(self, tmp_path: Path) -> None:
        preview = _preview()
        source = _job(tmp_path, preview)
        upload = _job(tmp_path, preview, job_id="upload-1", job_type="upload", status="running")
        store = _store_for(source, upload)
        album = MagicMock()
        album.productUrl = "https://photos.example/album-1"
        publisher = MagicMock()
        publisher.publish.return_value = album
        gp_factory = MagicMock(return_value=MagicMock())

        service = _service(store, publisher, MagicMock(), gp_factory)
        upload_id = service.start("job-1", access_token="ya29.tok")
        publisher.publish.assert_not_called()

        url = service.finish(upload_id, access_token="ya29.tok")

        assert url == "https://photos.example/album-1"
        publisher.publish.assert_called_once()
        store.mark_done.assert_called_once_with("upload-1", "https://photos.example/album-1")

    def test_publish_blank_token_raises_before_photos(self, tmp_path: Path) -> None:
        job = _job(tmp_path, _preview())
        store = MagicMock()
        store.get.return_value = job
        publisher = MagicMock()
        gp_factory = MagicMock()

        with pytest.raises(ValueError, match="google access token required"):
            _service(store, publisher, MagicMock(), gp_factory).publish(
                "job-1", access_token="   "
            )

        gp_factory.assert_not_called()
        publisher.publish.assert_not_called()
        store.create_upload_from.assert_not_called()
        store.set_status.assert_not_called()

    def test_publish_with_real_store_leaves_preview_and_isolates_events(
        self,
        tmp_path: Path,
    ) -> None:
        from src.jobs.events import JobEventBus
        from src.jobs.publish import PublishService
        from src.jobs.store import JobStore

        store = JobStore.load(tmp_path)
        preview_job = store.create(tmp_path)
        store.set_preview(preview_job.id, _preview())
        (preview_job.root / "hrimages").mkdir()
        (preview_job.root / "hrimages" / "20120802_01hr.JPG").write_bytes(b"\xff\xd8\xff\xd9")

        album = MagicMock()
        album.productUrl = "https://photos.example/album-1"
        publisher = MagicMock()
        publisher.publish.return_value = album
        events = JobEventBus(persist=store.append_event)

        service = PublishService(
            store=store,
            publisher=publisher,
            events=events,
            gp_factory=MagicMock(return_value=MagicMock()),
        )
        first_id = service.publish(preview_job.id, access_token="ya29.tok")
        second_id = service.publish(preview_job.id, access_token="ya29.tok")

        source = store.get(preview_job.id)
        assert source.id == preview_job.id
        assert source.type == "preview"
        assert source.status == "done"
        assert source.product_url is None
        assert [event.stage for event in source.events] == []

        first = store.get(first_id)
        second = store.get(second_id)
        assert first_id != preview_job.id
        assert second_id != preview_job.id
        assert first_id != second_id
        assert first.type == "upload"
        assert first.status == "done"
        assert first.product_url == "https://photos.example/album-1"
        assert first.root == source.root
        assert first.source_job_id == preview_job.id
        assert [event.stage for event in first.events] == ["publish", "done"]
        assert second.type == "upload"
        assert second.status == "done"
        assert [event.stage for event in second.events] == ["publish", "done"]
        assert publisher.publish.call_count == 2

