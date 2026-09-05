"""TDD: folder hub detection + fan-out into shared-artifact child previews."""
from __future__ import annotations

from pathlib import Path

from src.export.parser import AlbumExportParser
from src.jobs.events import JobEventBus
from src.jobs.folder_hub import (
    ALBUM_RELPATH_KEY,
    FolderAlbumKind,
    FolderHubDetector,
    FolderHubFanOut,
)
from src.jobs.ingest import IngestService
from src.jobs.store import (
    STATUS_DONE,
    STATUS_RUNNING,
    TYPE_PREVIEW,
    JobStore,
)
from src.jobs.workspace import JobWorkspace
from tests.support.suites import JobStoreSuite, TmpPathSuite


def _write_leaf(root: Path, *, title: str, item_id: str = "20120802_01") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "hrimages").mkdir(exist_ok=True)
    (root / "imagepages").mkdir(exist_ok=True)
    (root / "index.html").write_text(
        f"""<!DOCTYPE html>
<html><body>
  <span class="gallerytitle">{title}</span>
  <a href="imagepages/{item_id}.html"><img src="thumbnails/TN_{item_id}.JPG"></a>
</body></html>
""",
        encoding="utf-8",
    )
    (root / "imagepages" / f"{item_id}.html").write_text(
        f'<html><body><div class="imagetitle">{title} shot</div></body></html>',
        encoding="utf-8",
    )
    (root / "hrimages" / f"{item_id}hr.JPG").write_bytes(b"\xff\xd8\xff\xd9")


def _write_redirect_hub(root: Path, *, target: str = "./Aug10/index.html") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(
        f"""<!DOCTYPE html>
<html><head>
  <meta http-equiv="refresh" content="0;url={target}">
</head><body></body></html>
""",
        encoding="utf-8",
    )


class TestFolderHubDetector(TmpPathSuite):
    def test_redirect_hub_lists_sibling_leaf_dirs(self) -> None:
        hub = self.tmp_path / "0809_2"
        _write_redirect_hub(hub)
        _write_leaf(hub / "Aug10", title="Aug 10")
        _write_leaf(hub / "Aug11", title="Aug 11", item_id="20120811_01")
        (hub / "readme.txt").write_text("ignore", encoding="utf-8")

        plan = FolderHubDetector().detect(hub)

        assert plan.kind == FolderAlbumKind.HUB
        assert plan.child_relpaths == ("Aug10", "Aug11")

    def test_leaf_album_is_not_a_hub(self) -> None:
        leaf = self.tmp_path / "day1"
        _write_leaf(leaf, title="Day one")

        plan = FolderHubDetector().detect(leaf)

        assert plan.kind == FolderAlbumKind.LEAF
        assert plan.child_relpaths == ()

    def test_parent_with_child_indexes_but_no_photo_grid_is_hub(self) -> None:
        hub = self.tmp_path / "trip"
        hub.mkdir()
        (hub / "index.html").write_text(
            """<!DOCTYPE html>
<html><body>
  <span class="gallerytitle">Trip hub</span>
  <a href="Aug10/index.html">Day 10</a>
  <a href="Aug11/index.html">Day 11</a>
</body></html>
""",
            encoding="utf-8",
        )
        _write_leaf(hub / "Aug10", title="Aug 10")
        _write_leaf(hub / "Aug11", title="Aug 11", item_id="20120811_01")

        plan = FolderHubDetector().detect(hub)

        assert plan.kind == FolderAlbumKind.HUB
        assert plan.child_relpaths == ("Aug10", "Aug11")


class TestFolderHubFanOut(JobStoreSuite):
    def test_creates_shared_artifact_children_and_parses_leaves(self) -> None:
        store = JobStore.load(self.tmp_path)
        hub = self.tmp_path / "album_src"
        _write_redirect_hub(hub)
        _write_leaf(hub / "Aug10", title="Aug 10")
        _write_leaf(hub / "Aug11", title="Aug 11", item_id="20120811_01")

        parent = store.create(self.tmp_path, folder_label="0809_2")
        files = []
        for path in hub.rglob("*"):
            if path.is_file():
                rel = path.relative_to(hub).as_posix()
                files.append((rel, path.read_bytes(), None))
        store.materialize_album(parent.id, files)
        store.set_status(parent.id, STATUS_RUNNING, job_type=TYPE_PREVIEW)

        events = JobEventBus()
        ingest = IngestService(
            store=store,
            parser=AlbumExportParser(),
            events=events,
            workspace=JobWorkspace,
        )
        submitted: list[str] = []

        def submit(job_id: str, fn) -> None:
            submitted.append(job_id)
            fn()

        root = store.ensure_local_root(parent.id)
        plan = FolderHubDetector().detect(root)
        child_ids = FolderHubFanOut(
            store=store,
            jobs_root=self.tmp_path,
            submit=submit,
            run_child=lambda cid: ingest.finish_prepared(cid),
            events_emit=events.emit,
        ).apply(parent.id, plan)

        assert len(child_ids) == 2
        children = store.list_children(parent.id)
        assert {c.id for c in children} == set(child_ids)
        for child in children:
            assert child.type == TYPE_PREVIEW
            assert child.parent_job_id == parent.id
            assert child.source_job_id == parent.id
            assert (child.extra or {}).get(ALBUM_RELPATH_KEY) in {"Aug10", "Aug11"}
            assert child.status == STATUS_DONE
            assert child.preview is not None
            assert len(child.preview.items) == 1
            assert child.root.name in {"Aug10", "Aug11"}

        parent_after = store.get(parent.id)
        assert parent_after.status == STATUS_DONE
        assert set(submitted) == set(child_ids)

    def test_upload_from_hub_leaf_resolves_nested_media(self) -> None:
        store = JobStore.load(self.tmp_path)
        hub = self.tmp_path / "album_src"
        _write_redirect_hub(hub)
        _write_leaf(hub / "Aug19", title="Aug 19", item_id="0809_2_19_01")

        parent = store.create(self.tmp_path, folder_label="0809_2")
        files = []
        for path in hub.rglob("*"):
            if path.is_file():
                rel = path.relative_to(hub).as_posix()
                files.append((rel, path.read_bytes(), None))
        store.materialize_album(parent.id, files)
        store.set_status(parent.id, STATUS_RUNNING, job_type=TYPE_PREVIEW)

        events = JobEventBus()
        ingest = IngestService(
            store=store,
            parser=AlbumExportParser(),
            events=events,
            workspace=JobWorkspace,
        )

        def submit(job_id: str, fn) -> None:
            fn()

        root = store.ensure_local_root(parent.id)
        plan = FolderHubDetector().detect(root)
        child_ids = FolderHubFanOut(
            store=store,
            jobs_root=self.tmp_path,
            submit=submit,
            run_child=lambda cid: ingest.finish_prepared(cid),
            events_emit=events.emit,
        ).apply(parent.id, plan)
        assert len(child_ids) == 1
        leaf = store.get(child_ids[0])
        assert leaf.preview is not None
        item = leaf.preview.items[0]
        assert item.relpath == "hrimages/0809_2_19_01hr.JPG"

        upload = store.create_upload_from(leaf.id)
        assert (upload.extra or {}).get(ALBUM_RELPATH_KEY) == "Aug19"
        assert upload.root.name == "Aug19"
        resolved = store.ensure_artifact_file(upload.id, item.relpath)
        assert resolved.is_file()
        assert resolved.stat().st_size > 0
        assert resolved.as_posix().endswith("Aug19/hrimages/0809_2_19_01hr.JPG")
