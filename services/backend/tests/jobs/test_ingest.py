"""TDD: IngestService materializes an upload, parses preview, and emits job events."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from src.export.preview import AlbumPreview, PreviewItem
from tests.support.builders import PreviewBuilder, PreviewItemBuilder
from tests.support.suites import MockJobServiceSuite

FileTuple = Tuple[str, bytes, Optional[float]]


def _preview() -> AlbumPreview:
    return (
        PreviewBuilder()
        .with_title("Mini album")
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


def _files() -> List[FileTuple]:
    return [
        ("index.html", b"<html></html>", None),
        ("hrimages/a.jpg", b"jpeg", 1343901600.0),
    ]


def _job(tmp_path: Path) -> MagicMock:
    job = MagicMock()
    job.id = "job-1"
    job.root = tmp_path / "jobs" / "job-1"
    job.status = "pending"
    job.type = "preview"
    job.owner_id = None
    return job


def _service(
    store: MagicMock,
    parser: MagicMock,
    events: MagicMock,
    workspace: MagicMock,
):
    from src.jobs.ingest import IngestService

    return IngestService(
        store=store,
        parser=parser,
        events=events,
        workspace=workspace,
    )


def _emit_stages(events: MagicMock) -> List[str]:
    return [call.args[1] for call in events.emit.call_args_list]

class TestIngestService(MockJobServiceSuite):
    def test_ingest_module_exports_service(self) -> None:
        from src.jobs.ingest import IngestService

        assert IngestService is not None

    def test_ingest_happy_path_materialize_parse_preview_and_events(self, tmp_path: Path) -> None:
        files = _files()
        preview = _preview()
        job = _job(tmp_path)
        jobs_root = tmp_path / "jobs"

        store = MagicMock()
        store.create.return_value = job
        store.get.return_value = job
        store.find_by_title.return_value = None

        parser = MagicMock()
        parser.parse.return_value = preview

        events = MagicMock()
        workspace = MagicMock()
        workspace.return_value.materialize.return_value = job.root

        order: list[str] = []
        events.emit.side_effect = lambda *args, **kwargs: order.append(
            f"emit:{args[1]}"
        )
        store.set_preview.side_effect = lambda *args, **kwargs: order.append(
            "set_preview"
        )

        job_id = _service(store, parser, events, workspace).ingest(
            files, jobs_root=jobs_root
        )

        assert job_id == "job-1"
        store.create.assert_called_once_with(jobs_root, owner_id=None)
        store.materialize_album.assert_called_once_with("job-1", files)
        workspace.assert_not_called()

        parser.parse.assert_called_once()
        parse_args, parse_kwargs = parser.parse.call_args
        assert parse_args[0] == job.root
        assert parse_kwargs.get("allow_loose_media") is True
        sink = parse_kwargs.get("sink")
        if sink is None and len(parse_args) > 1:
            sink = parse_args[1]
        assert sink is not None
        assert callable(getattr(sink, "emit", None))

        store.set_preview.assert_called_once_with("job-1", preview, warnings=[])
        store.set_status.assert_called_once_with(
            "job-1", "running", job_type="preview"
        )

        stages = _emit_stages(events)
        assert "ingest" in stages
        assert "preview_ready" in stages
        assert "error" not in stages
        assert all(call.args[0] == "job-1" for call in events.emit.call_args_list)
        assert order.index("emit:preview_ready") < order.index("set_preview")

    def test_ingest_parser_sink_forwards_to_event_bus(self, tmp_path: Path) -> None:
        preview = _preview()
        job = _job(tmp_path)

        store = MagicMock()
        store.create.return_value = job
        store.get.return_value = job
        store.find_by_title.return_value = None

        def parse_impl(
            root: Path, sink=None, *, allow_loose_media: bool = False
        ) -> AlbumPreview:
            assert sink is not None
            assert allow_loose_media is True
            sink.emit("parse", "Parsing album export", current=0, total=1)
            sink.emit("parse", "hrimages/a.jpg", current=1, total=1)
            return preview

        parser = MagicMock()
        parser.parse.side_effect = parse_impl

        events = MagicMock()
        workspace = MagicMock()

        _service(store, parser, events, workspace).ingest(
            _files(), jobs_root=tmp_path / "jobs"
        )

        parse_emits = [
            call
            for call in events.emit.call_args_list
            if call.args[1] == "parse"
        ]
        assert parse_emits
        assert parse_emits[0].args[0] == "job-1"
        assert parse_emits[0].kwargs.get("current", 0) == 0
        assert parse_emits[0].kwargs.get("total", 0) == 1
        assert parse_emits[-1].kwargs.get("current") == 1
        assert parse_emits[-1].kwargs.get("total") == 1

    def test_ingest_parse_failure_sets_error_status_emits_and_reraises(
        self,
        tmp_path: Path,
    ) -> None:
        job = _job(tmp_path)

        store = MagicMock()
        store.create.return_value = job
        store.get.return_value = job
        store.find_by_title.return_value = None

        parser = MagicMock()
        parser.parse.side_effect = ValueError(
            "Can't process album as there is no 'index.html' file"
        )

        events = MagicMock()
        workspace = MagicMock()

        with pytest.raises(RuntimeError, match="ingest failed at parse"):
            _service(store, parser, events, workspace).ingest(
                _files(), jobs_root=tmp_path / "jobs"
            )

        store.set_preview.assert_not_called()
        status_calls = store.set_status.call_args_list
        assert status_calls
        assert status_calls[0].args[0] == "job-1"
        assert status_calls[0].args[1] == "running"
        status_args, status_kwargs = status_calls[-1]
        assert status_args[0] == "job-1"
        assert status_args[1] == "failed"
        error = status_kwargs.get("error")
        if error is None and len(status_args) > 2:
            error = status_args[2]
        assert error is not None
        assert "index.html" in str(error)
        assert "ingest failed at parse" in str(error)

        stages = _emit_stages(events)
        assert "error" in stages
        assert "preview_ready" not in stages
        error_calls = [
            call for call in events.emit.call_args_list if call.args[1] == "error"
        ]
        assert error_calls
        assert error_calls[0].args[0] == "job-1"
        assert "index.html" in error_calls[0].args[2]

    def test_ingest_without_overwrite_raises_when_title_matches(self, tmp_path: Path) -> None:
        from src.jobs.ingest import AlbumExistsError

        files = _files()
        preview = _preview()
        new_job = _job(tmp_path)
        existing = MagicMock()
        existing.id = "job-existing"
        existing.root = tmp_path / "jobs" / "job-existing"
        existing.status = "done"
        existing.type = "upload"
        existing.product_url = "https://photos.example/album-1"
        existing.owner_id = None
        existing.root.mkdir(parents=True, exist_ok=True)
        (existing.root / "stale.txt").write_text("old", encoding="utf-8")

        store = MagicMock()
        store.create.return_value = new_job
        store.get.return_value = new_job
        store.find_by_title.return_value = existing

        parser = MagicMock()
        parser.parse.return_value = preview

        events = MagicMock()
        workspace = MagicMock()
        workspace.return_value.materialize.return_value = new_job.root

        with pytest.raises(AlbumExistsError) as exc_info:
            _service(store, parser, events, workspace).ingest(
                files, jobs_root=tmp_path / "jobs"
            )

        assert exc_info.value.existing_id == "job-existing"
        assert exc_info.value.title == preview.title
        store.find_by_title.assert_called_with(preview.title, owner_id=None)
        store.delete.assert_called_once_with("job-1")
        store.set_preview.assert_not_called()
        store.set_status.assert_called_once_with(
            "job-1", "running", job_type="preview"
        )
        store.delete_duplicates_for_title.assert_not_called()
        assert (existing.root / "stale.txt").exists()
        preview_ready = [
            call for call in events.emit.call_args_list if call.args[1] == "preview_ready"
        ]
        assert not preview_ready

    def test_ingest_with_overwrite_reuses_existing_job_when_title_matches(
        self,
        tmp_path: Path,
    ) -> None:
        files = _files()
        preview = _preview()
        new_job = _job(tmp_path)
        existing = MagicMock()
        existing.id = "job-existing"
        existing.root = tmp_path / "jobs" / "job-existing"
        existing.status = "done"
        existing.type = "upload"
        existing.product_url = "https://photos.example/album-1"
        existing.owner_id = None
        existing.root.mkdir(parents=True, exist_ok=True)
        (existing.root / "stale.txt").write_text("old", encoding="utf-8")

        store = MagicMock()
        store.create.return_value = new_job
        store.get.side_effect = lambda job_id, **kwargs: (
            existing if job_id == "job-existing" else new_job
        )
        store.find_by_title.return_value = existing
        store.materialize_album.return_value = existing.root

        parser = MagicMock()
        parser.parse.return_value = preview

        events = MagicMock()
        workspace = MagicMock()

        job_id = _service(store, parser, events, workspace).ingest(
            files, jobs_root=tmp_path / "jobs", overwrite=True
        )

        assert job_id == "job-existing"
        store.find_by_title.assert_called_with(preview.title, owner_id=None)
        store.set_status.assert_any_call("job-1", "running", job_type="preview")
        store.set_preview.assert_called_once_with(
            "job-existing", preview, warnings=[]
        )
        store.delete.assert_called_once_with("job-1")
        store.materialize_album.assert_called()
        workspace.assert_not_called()
        preview_ready = [
            call for call in events.emit.call_args_list if call.args[1] == "preview_ready"
        ]
        assert preview_ready
        assert preview_ready[-1].args[0] == "job-existing"
        assert not (existing.root / "stale.txt").exists()

    def test_ingest_sets_structure_fallback_warning(self, tmp_path: Path) -> None:
        from src.export.parser import STRUCTURE_FALLBACK_WARNING

        preview = AlbumPreview(
            title="VacationPics",
            description=None,
            multi_index=False,
            items=(
                PreviewItem(
                    id="photo_a",
                    relpath="photo_a.jpg",
                    caption="",
                    size_bytes=4,
                ),
            ),
            structure_fallback=True,
        )
        job = _job(tmp_path)
        store = MagicMock()
        store.create.return_value = job
        store.get.return_value = job
        store.find_by_title.return_value = None
        parser = MagicMock()
        parser.parse.return_value = preview
        events = MagicMock()
        workspace = MagicMock()

        _service(store, parser, events, workspace).ingest(
            [("photo_a.jpg", b"jpeg", None)], jobs_root=tmp_path / "jobs"
        )

        store.set_preview.assert_called_once_with(
            "job-1", preview, warnings=[STRUCTURE_FALLBACK_WARNING]
        )

