"""AutoPublisher: remember token, launch upload after preview, never persist token."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.export.preview import AlbumPreview
from src.jobs.autopublish import AutoPublisher
from src.jobs.events import JobEventBus
from src.jobs.store import JobStore
from src.jobs.tokens import AccessTokenVault
from tests.support.builders import PreviewBuilder, PreviewItemBuilder
from tests.support.suites import JobStoreSuite


def _preview_with_items() -> AlbumPreview:
    return (
        PreviewBuilder()
        .with_title("Day 1")
        .no_journal()
        .with_items(
            PreviewItemBuilder()
            .with_size(4)
            .with_last_modified(None)
            .with_taken_on(None)
            .build()
        )
        .build()
    )


def _publisher(
    tmp_path: Path,
    *,
    publish: MagicMock | None = None,
) -> tuple[AutoPublisher, JobStore, MagicMock, JobEventBus]:
    store = JobStore.load(tmp_path)
    bus = JobEventBus(persist=store.append_event)
    mock_publish = publish or MagicMock()
    mock_publish.launch.return_value = "upload-1"
    service = AutoPublisher(store=store, publish=mock_publish, events=bus)
    return service, store, mock_publish, bus

class TestAutoPublisher(JobStoreSuite):
    def test_remember_and_discard(self) -> None:
        vault = AccessTokenVault()
        service = AutoPublisher(
            store=MagicMock(),
            publish=MagicMock(),
            events=MagicMock(),
            vault=vault,
        )
        service.remember("job-1", "  ya29.tok  ")
        assert vault.get("job-1") == "ya29.tok"
        service.discard("job-1")
        assert vault.get("job-1") is None

    def test_after_preview_missing_jobs_discards_token(self, tmp_path: Path) -> None:
        service, _store, publish, _bus = _publisher(tmp_path)
        service.remember("token-key", "ya29.tok")
        assert service.after_preview("missing", parent_id="also-missing", token_key="token-key") is None
        publish.launch.assert_not_called()

    def test_after_preview_not_flagged_returns_none(self, tmp_path: Path) -> None:
        service, store, publish, _bus = _publisher(tmp_path)
        preview = store.create(tmp_path)
        parent = store.create(tmp_path, job_type="scrape", scrape_url="https://albums.example/a")
        store.set_preview(preview.id, _preview_with_items())
        assert (
            service.after_preview(preview.id, parent_id=parent.id, token_key="unused") is None
        )
        publish.launch.assert_not_called()

    def test_after_preview_cancelled_preview_skips(self, tmp_path: Path) -> None:
        service, store, publish, _bus = _publisher(tmp_path)
        preview = store.create(tmp_path, auto_publish=True)
        parent = store.create(
            tmp_path, job_type="scrape", scrape_url="https://albums.example/a", auto_publish=True
        )
        store.set_preview(preview.id, _preview_with_items())
        store.set_status(preview.id, "cancelled", job_type="preview")
        service.remember(parent.id, "ya29.tok")
        assert service.after_preview(preview.id, parent_id=parent.id, token_key=parent.id) is None
        publish.launch.assert_not_called()

    def test_after_preview_failed_preview_skips(self, tmp_path: Path) -> None:
        service, store, publish, _bus = _publisher(tmp_path)
        preview = store.create(tmp_path, auto_publish=True)
        parent = store.create(
            tmp_path, job_type="scrape", scrape_url="https://albums.example/a", auto_publish=True
        )
        store.set_preview(preview.id, _preview_with_items())
        store.set_status(preview.id, "failed", error="boom", job_type="preview")
        service.remember(parent.id, "ya29.tok")
        assert service.after_preview(preview.id, parent_id=parent.id, token_key=parent.id) is None
        publish.launch.assert_not_called()

    def test_after_preview_cancelled_parent_skips(self, tmp_path: Path) -> None:
        service, store, publish, _bus = _publisher(tmp_path)
        preview = store.create(tmp_path, auto_publish=True)
        parent = store.create(
            tmp_path, job_type="scrape", scrape_url="https://albums.example/a", auto_publish=True
        )
        store.set_preview(preview.id, _preview_with_items())
        store.set_status(parent.id, "cancelled", job_type="scrape")
        service.remember(parent.id, "ya29.tok")
        assert service.after_preview(preview.id, parent_id=parent.id, token_key=parent.id) is None
        publish.launch.assert_not_called()

    def test_after_preview_empty_items_skips(self, tmp_path: Path) -> None:
        service, store, publish, _bus = _publisher(tmp_path)
        preview = store.create(tmp_path, auto_publish=True)
        parent = store.create(
            tmp_path, job_type="scrape", scrape_url="https://albums.example/a", auto_publish=True
        )
        store.set_preview(
            preview.id,
            AlbumPreview(title="Empty", description=None, multi_index=False, items=()),
        )
        service.remember(parent.id, "ya29.tok")
        assert service.after_preview(preview.id, parent_id=parent.id, token_key=parent.id) is None
        publish.launch.assert_not_called()

    def test_after_preview_missing_token_emits_skip(self, tmp_path: Path) -> None:
        service, store, publish, _bus = _publisher(tmp_path)
        preview = store.create(tmp_path)
        parent = store.create(
            tmp_path, job_type="scrape", scrape_url="https://albums.example/a", auto_publish=True
        )
        store.set_preview(preview.id, _preview_with_items())
        assert service.after_preview(preview.id, parent_id=parent.id, token_key="no-token") is None
        publish.launch.assert_not_called()
        stages = [event.stage for event in store.get(parent.id).events]
        assert "auto_publish" in stages

    def test_after_preview_launch_failure_emits(self, tmp_path: Path) -> None:
        publish = MagicMock()
        publish.launch.side_effect = RuntimeError("google down")
        service, store, _, _bus = _publisher(tmp_path, publish=publish)
        preview = store.create(tmp_path)
        parent = store.create(
            tmp_path, job_type="scrape", scrape_url="https://albums.example/a", auto_publish=True
        )
        store.set_preview(preview.id, _preview_with_items())
        service.remember(parent.id, "ya29.tok")
        assert service.after_preview(preview.id, parent_id=parent.id, token_key=parent.id) is None
        events = store.get(parent.id).events
        assert any(event.stage == "auto_publish" for event in events)
        assert any("failed" in event.message for event in events)

    def test_after_preview_none_preview_skips(self, tmp_path: Path) -> None:
        service, store, publish, _bus = _publisher(tmp_path)
        preview = store.create(tmp_path, auto_publish=True)
        parent = store.create(
            tmp_path, job_type="scrape", scrape_url="https://albums.example/a", auto_publish=True
        )
        service.remember(parent.id, "ya29.tok")
        assert service.after_preview(preview.id, parent_id=parent.id, token_key=parent.id) is None
        publish.launch.assert_not_called()

    def test_after_preview_status_cancelled_when_is_cancelled_false(self) -> None:
        store = MagicMock()
        preview = MagicMock()
        preview.status = "cancelled"
        preview.auto_publish = True
        preview.preview = _preview_with_items()
        parent = MagicMock()
        parent.status = "running"
        parent.auto_publish = True
        store.get.side_effect = lambda job_id: preview if job_id == "p" else parent
        store.is_cancelled.return_value = False
        publish = MagicMock()
        service = AutoPublisher(store=store, publish=publish, events=MagicMock())
        service.remember("k", "ya29.tok")
        assert service.after_preview("p", parent_id="parent", token_key="k") is None
        publish.launch.assert_not_called()

    def test_after_preview_parent_status_cancelled_when_is_cancelled_false(self) -> None:
        store = MagicMock()
        preview = MagicMock()
        preview.status = "done"
        preview.auto_publish = True
        preview.preview = _preview_with_items()
        parent = MagicMock()
        parent.status = "cancelled"
        parent.auto_publish = True
        store.get.side_effect = lambda job_id: preview if job_id == "p" else parent
        store.is_cancelled.return_value = False
        publish = MagicMock()
        service = AutoPublisher(store=store, publish=publish, events=MagicMock())
        service.remember("k", "ya29.tok")
        assert service.after_preview("p", parent_id="parent", token_key="k") is None
        publish.launch.assert_not_called()

    def test_after_preview_happy_path_launches(self, tmp_path: Path) -> None:
        service, store, publish, _bus = _publisher(tmp_path)
        preview = store.create(tmp_path)
        parent = store.create(
            tmp_path, job_type="scrape", scrape_url="https://albums.example/a", auto_publish=True
        )
        store.set_preview(preview.id, _preview_with_items())
        service.remember(parent.id, "ya29.tok")
        upload_id = service.after_preview(
            preview.id, parent_id=parent.id, token_key=parent.id
        )
        assert upload_id == "upload-1"
        publish.launch.assert_called_once_with(
            preview.id, access_token="ya29.tok", parent_job_id=parent.id
        )

