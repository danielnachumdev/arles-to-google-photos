"""TDD: ReprocessService reparses an existing job root without a new upload."""
from __future__ import annotations

from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import pytest

from src.export.preview import AlbumPreview, PreviewItem
from tests.support.builders import PreviewBuilder, PreviewItemBuilder
from src.jobs.store import JobNotFoundError
from tests.support.suites import MockJobServiceSuite


def _preview(title: str = "Reparsed") -> AlbumPreview:
    return (
        PreviewBuilder()
        .with_title(title)
        .no_journal()
        .with_items(
            PreviewItemBuilder()
            .with_caption("hello")
            .with_size(4)
            .with_last_modified(None)
            .with_taken_on(None)
            .build()
        )
        .build()
    )


def _job(tmp_path: Path, preview: AlbumPreview | None = None) -> MagicMock:
    job = MagicMock()
    job.id = "job-1"
    job.root = tmp_path / "jobs" / "job-1"
    job.status = "done" if preview is not None else "pending"
    job.type = "preview"
    job.preview = preview
    job.error = None
    job.product_url = "https://photos.example/album-1" if preview is not None else None
    return job


def _service(store: MagicMock, parser: MagicMock, events: MagicMock):
    from src.jobs.reprocess import ReprocessService

    return ReprocessService(store=store, parser=parser, events=events)


def _emit_stages(events: MagicMock) -> List[str]:
    return [call.args[1] for call in events.emit.call_args_list]

class TestReprocessService(MockJobServiceSuite):
    def test_reprocess_module_exports_service(self) -> None:
        from src.jobs.reprocess import ReprocessService

        assert ReprocessService is not None

    def test_reprocess_applies_title_prefix_before_set_preview(self, tmp_path: Path) -> None:
        preview = _preview("Parsed")
        job = _job(tmp_path, preview=_preview("Old"))
        store = MagicMock()
        store.get.return_value = job
        parser = MagicMock()
        parser.parse.return_value = preview
        events = MagicMock()

        job_id = _service(store, parser, events).reprocess(
            "job-1", title_prefix="Reprocessed · ", title_base="Edited title"
        )

        assert job_id == "job-1"
        store.set_preview.assert_called_once()
        saved = store.set_preview.call_args.args[1]
        assert saved.title == "Reprocessed · Edited title"

    def test_start_new_preview_reprocess_copies_artifacts_and_submits(
        self,
        tmp_path: Path,
    ) -> None:
        from src.jobs.reprocess import start_new_preview_reprocess
        from src.jobs.store import JobStore

        store = JobStore.load(tmp_path)
        source = store.create(tmp_path, folder_label="Day1")
        store.set_preview(source.id, _preview("Original"))
        store.update_preview(source.id, _preview("Edited title"))
        (source.root / "index.html").write_text("<html></html>", encoding="utf-8")
        assert store.get(source.id).user_edited is True

        submitted: list[str] = []
        reprocess = MagicMock()

        def submit(job_id: str, fn):
            submitted.append(job_id)
            fn()

        new_id = start_new_preview_reprocess(
            store,
            tmp_path,
            store.get(source.id),
            title_prefix="Reprocessed · ",
            submit=submit,
            reprocess=reprocess,
        )

        assert new_id != source.id
        assert submitted == [new_id]
        reprocess.reprocess.assert_called_once_with(
            new_id, title_prefix="Reprocessed · ", title_base="Edited title"
        )
        kept = store.get(source.id)
        assert kept.preview is not None
        assert kept.preview.title == "Edited title"
        assert kept.user_edited is True
        assert (store.get(new_id).root / "index.html").is_file()

    def test_reprocess_reparses_existing_root_without_create(self, tmp_path: Path) -> None:
        preview = _preview()
        job = _job(tmp_path, preview=_preview("Old"))
        store = MagicMock()
        store.get.return_value = job
        store.ensure_local_root.return_value = job.root
        parser = MagicMock()
        parser.parse.return_value = preview
        events = MagicMock()

        job_id = _service(store, parser, events).reprocess("job-1")

        assert job_id == "job-1"
        store.get.assert_called_once_with("job-1")
        store.ensure_local_root.assert_called_once_with("job-1")
        parser.parse.assert_called_once()
        parse_args, parse_kwargs = parser.parse.call_args
        assert parse_args[0] == job.root
        sink = parse_kwargs.get("sink")
        if sink is None and len(parse_args) > 1:
            sink = parse_args[1]
        assert sink is not None
        assert callable(getattr(sink, "emit", None))
        store.set_status.assert_called_once_with(
            "job-1", "running", job_type="preview"
        )
        store.set_preview.assert_called_once_with("job-1", preview, warnings=[])
        store.create.assert_not_called()

        stages = _emit_stages(events)
        assert "preview_ready" in stages
        assert "error" not in stages

    def test_reprocess_missing_job_raises(self, tmp_path: Path) -> None:
        store = MagicMock()
        store.get.side_effect = JobNotFoundError("missing")
        with pytest.raises(JobNotFoundError):
            _service(store, MagicMock(), MagicMock()).reprocess("missing")

    def test_reprocess_upload_job_raises_without_parsing(self, tmp_path: Path) -> None:
        job = _job(tmp_path, preview=_preview("Old"))
        job.type = "upload"
        store = MagicMock()
        store.get.return_value = job
        parser = MagicMock()

        with pytest.raises(ValueError, match="reprocess is only for preview jobs"):
            _service(store, parser, MagicMock()).reprocess("job-1")

        parser.parse.assert_not_called()
        store.set_preview.assert_not_called()

    def test_reprocess_parse_failure_sets_error_status_emits_and_reraises(
        self,
        tmp_path: Path,
    ) -> None:
        job = _job(tmp_path, preview=_preview("Old"))
        store = MagicMock()
        store.get.return_value = job
        parser = MagicMock()
        parser.parse.side_effect = ValueError(
            "Can't process album as there is no 'index.html' file"
        )
        events = MagicMock()

        with pytest.raises(ValueError, match="index.html"):
            _service(store, parser, events).reprocess("job-1")

        store.set_preview.assert_not_called()
        status_calls = store.set_status.call_args_list
        assert status_calls
        assert status_calls[0].args[1] == "running"
        status_args, status_kwargs = status_calls[-1]
        assert status_args[0] == "job-1"
        assert status_args[1] == "failed"
        error = status_kwargs.get("error")
        if error is None and len(status_args) > 2:
            error = status_args[2]
        assert error is not None
        assert "index.html" in str(error)

        stages = _emit_stages(events)
        assert "error" in stages
        assert "preview_ready" not in stages

    def test_job_is_web_origin_uses_import_origin_then_infers(self) -> None:
        from src.jobs.reprocess import job_is_web_origin

        folder = MagicMock()
        folder.import_origin = "folder"
        folder.type = "preview"
        folder.parent_job_id = None
        folder.scrape_url = None
        assert job_is_web_origin(folder) is False

        explicit_web = MagicMock()
        explicit_web.import_origin = "web"
        explicit_web.type = "preview"
        explicit_web.parent_job_id = None
        explicit_web.scrape_url = None
        assert job_is_web_origin(explicit_web) is True

        inferred = MagicMock()
        inferred.import_origin = None
        inferred.type = "preview"
        inferred.parent_job_id = "scrape-1"
        inferred.scrape_url = None
        assert job_is_web_origin(inferred) is True

        scrape = MagicMock()
        scrape.import_origin = None
        scrape.type = "scrape"
        scrape.parent_job_id = None
        scrape.scrape_url = "https://albums.example/day1"
        assert job_is_web_origin(scrape) is True

    def test_leaf_scrape_id_retries_parent_leaf_not_hub(self) -> None:
        from src.jobs.reprocess import leaf_scrape_id_for_reprocess
        from src.jobs.store import JobNotFoundError

        preview = MagicMock()
        preview.id = "preview-1"
        preview.type = "preview"
        preview.parent_job_id = "leaf-1"

        leaf = MagicMock()
        leaf.id = "leaf-1"
        leaf.type = "scrape"
        leaf.scrape_url = "https://albums.example/day1"

        hub_preview = MagicMock()
        hub_preview.id = "hub-preview"
        hub_preview.type = "preview"
        hub_preview.parent_job_id = "hub-1"

        hub = MagicMock()
        hub.id = "hub-1"
        hub.type = "scrape"
        hub.scrape_url = "https://albums.example/hub/"

        hub_child = MagicMock()
        hub_child.id = "leaf-1"
        hub_child.type = "scrape"

        store = MagicMock()

        def _get(job_id: str):
            if job_id == "leaf-1":
                return leaf
            if job_id == "hub-1":
                return hub
            raise JobNotFoundError(job_id)

        store.get.side_effect = _get
        store.list_children.side_effect = lambda parent_id: (
            [hub_child] if parent_id == "hub-1" else []
        )

        assert leaf_scrape_id_for_reprocess(store, preview) == "leaf-1"
        assert leaf_scrape_id_for_reprocess(store, hub_preview) is None

        scrape = MagicMock()
        scrape.id = "scrape-1"
        scrape.type = "scrape"
        assert leaf_scrape_id_for_reprocess(store, scrape) == "scrape-1"

        orphan = MagicMock()
        orphan.type = "preview"
        orphan.parent_job_id = "missing-parent"
        assert leaf_scrape_id_for_reprocess(store, orphan) is None

        no_parent = MagicMock()
        no_parent.type = "preview"
        no_parent.parent_job_id = None
        assert leaf_scrape_id_for_reprocess(store, no_parent) is None

        parent_not_scrape = MagicMock()
        parent_not_scrape.type = "preview"
        parent_not_scrape.parent_job_id = "preview-1"
        preview_as_parent = MagicMock()
        preview_as_parent.type = "preview"
        preview_as_parent.id = "preview-1"

        def _get2(job_id: str):
            if job_id == "preview-1":
                return preview_as_parent
            return _get(job_id)

        store.get.side_effect = _get2
        assert leaf_scrape_id_for_reprocess(store, parent_not_scrape) is None

        leaf_no_url = MagicMock()
        leaf_no_url.id = "leaf-nourl"
        leaf_no_url.type = "scrape"
        leaf_no_url.scrape_url = None
        preview_nourl = MagicMock()
        preview_nourl.type = "preview"
        preview_nourl.parent_job_id = "leaf-nourl"

        def _get3(job_id: str):
            if job_id == "leaf-nourl":
                return leaf_no_url
            return _get2(job_id)

        store.get.side_effect = _get3
        assert leaf_scrape_id_for_reprocess(store, preview_nourl) is None

    def test_resolve_title_prefix_defaults(self) -> None:
        from src.jobs.reprocess import DEFAULT_TITLE_PREFIX, resolve_title_prefix

        assert resolve_title_prefix(None) == DEFAULT_TITLE_PREFIX
        assert resolve_title_prefix("Custom · ") == "Custom · "

    def test_reprocess_cancel_marks_cancelled(self, tmp_path: Path) -> None:
        from src.progress import JobCancelled

        preview = _preview()
        job = _job(tmp_path, preview=_preview("Old"))
        store = MagicMock()
        store.get.return_value = job
        store.is_cancelled.return_value = True
        parser = MagicMock()
        parser.parse.side_effect = JobCancelled()
        events = MagicMock()

        job_id = _service(store, parser, events).reprocess("job-1")
        assert job_id == "job-1"
        assert store.set_status.call_args_list[-1].kwargs.get("job_type") == "preview"
        assert store.set_status.call_args_list[-1].args[1] == "cancelled"

