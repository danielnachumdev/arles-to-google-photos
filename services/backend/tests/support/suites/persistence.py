"""StateStore + ArtifactStore contract suites. Not collected (no Test prefix)."""
from __future__ import annotations

from abc import ABC
from datetime import datetime, timezone
from pathlib import Path

import pytest
from gp_wrapper.utils import FileTimeService

from src.export.parser import AlbumExportParser
from src.export.preview import AlbumPreview
from src.jobs.persistence.artifacts import ArtifactStore
from src.jobs.persistence.state import JobRecord
from src.jobs.store import JOB_META_NAME
from tests.conftest import DAY1_MINI
from tests.support.builders import JobRecordBuilder, PreviewBuilder
from tests.support.persistence import StateStoreBackend
from tests.support.suites.tmp import TmpPathSuite


class ArtifactStoreSuite(TmpPathSuite):
    """fs vs gcs ArtifactStore contract. Subclass and implement ``make_store``."""

    JPEG_BYTES = b"\xff\xd8\xff\xd9"
    HTML_BYTES = b"<html><body>index</body></html>"
    artifacts: ArtifactStore

    def make_store(self, tmp_path: Path) -> ArtifactStore:
        raise NotImplementedError

    @pytest.fixture(autouse=True)
    def _bind_artifacts(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.artifacts = self.make_store(tmp_path)

    def test_materialize_writes_nested_relpaths(self) -> None:
        returned = self.artifacts.materialize(
            "job-1",
            [
                ("hrimages/a.jpg", self.JPEG_BYTES, None),
                ("index.html", self.HTML_BYTES, None),
            ],
        )

        root = self.artifacts.local_root("job-1")
        assert returned == root
        assert (root / "index.html").read_bytes() == self.HTML_BYTES
        assert self.artifacts.exists("job-1", "hrimages/a.jpg")
        assert (
            self.artifacts.ensure_file("job-1", "hrimages/a.jpg").read_bytes()
            == self.JPEG_BYTES
        )

    def test_put_writes_single_file(self) -> None:
        self.artifacts.put("job-1", "imagepages/a.html", self.HTML_BYTES)
        assert self.artifacts.exists("job-1", "imagepages/a.html")
        assert self.artifacts.ensure_file(
            "job-1", "imagepages/a.html"
        ).read_bytes() == self.HTML_BYTES

    def test_materialize_applies_last_modified(self) -> None:
        stamp = datetime(2012, 8, 2, 12, 0, 0).timestamp()
        self.artifacts.materialize("job-1", [("hrimages/a.jpg", self.JPEG_BYTES, stamp)])

        path = self.artifacts.ensure_file("job-1", "hrimages/a.jpg")
        got = FileTimeService().get(str(path))
        assert got.modification is not None
        assert abs(got.modification.timestamp() - stamp) <= 2

    def test_materialize_rejects_path_traversal(self) -> None:
        with pytest.raises(ValueError, match="traversal"):
            self.artifacts.materialize("job-1", [("../secret", b"leaked", None)])
        assert not (self.tmp_path / "secret").exists()
        with pytest.raises(ValueError, match="traversal"):
            self.artifacts.put("job-1", r"..\secret", b"leaked")
        assert not (self.tmp_path / "secret").exists()

    def test_delete_job_removes_tree_not_other_jobs(self) -> None:
        self.artifacts.materialize("keep", [("index.html", self.HTML_BYTES, None)])
        self.artifacts.materialize(
            "drop",
            [("index.html", self.HTML_BYTES, None), ("hrimages/a.jpg", self.JPEG_BYTES, None)],
        )
        (self.artifacts.local_root("drop") / JOB_META_NAME).write_text("{}", encoding="utf-8")

        self.artifacts.delete_job("drop")

        assert not self.artifacts.local_root("drop").exists()
        assert self.artifacts.exists("keep", "index.html")

    def test_list_returns_relpaths_skips_state_files(self) -> None:
        self.artifacts.materialize(
            "job-1",
            [
                ("index.html", self.HTML_BYTES, None),
                ("hrimages/a.jpg", self.JPEG_BYTES, None),
            ],
        )
        (self.artifacts.local_root("job-1") / JOB_META_NAME).write_text(
            "{}", encoding="utf-8"
        )

        listed = set(self.artifacts.list("job-1"))
        assert listed == {"index.html", "hrimages/a.jpg"}

    def test_local_root_usable_by_parser(self) -> None:
        files = []
        for rel in (
            "index.html",
            "hrimages/20120802_01hr.JPG",
            "imagepages/20120802_01.html",
        ):
            files.append((rel, (DAY1_MINI / rel).read_bytes(), None))
        self.artifacts.materialize("job-1", files)

        preview = AlbumExportParser().parse(self.artifacts.local_root("job-1"))
        assert preview.title == "2/8/2012 - mini fixture"
        assert len(preview.items) == 1
        assert preview.items[0].id == "20120802_01"

    def test_invalid_job_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            self.artifacts.local_root("../outside")
        with pytest.raises(ValueError):
            self.artifacts.delete_job("..")

    def test_exists_rejects_traversal_and_list_missing_job(self) -> None:
        assert self.artifacts.exists("job-1", "../secret") is False
        assert self.artifacts.list("missing-job") == []


class StateStoreSuite(TmpPathSuite, ABC):
    """Strategy suite: subclass, set ``backend``, inherit contract tests.

    ``setup_method`` creates ``self.state``. Also exposes ``state`` fixture
    for tests that still request it by name.
    """

    backend: StateStoreBackend

    @pytest.fixture(autouse=True)
    def state(self, tmp_path: Path):
        self.tmp_path = tmp_path
        store = self.backend.create(tmp_path)
        self.state = store
        return store

    def preview(self, title: str = "Album") -> AlbumPreview:
        return PreviewBuilder().with_title(title).build()

    def record(
        self,
        job_id: str = "job-1",
        *,
        status: str = "pending",
        job_type: str = "preview",
        preview: AlbumPreview | None = None,
        error: str | None = None,
        product_url: str | None = None,
        folder_label: str | None = None,
        created_at: datetime | None = None,
        source_job_id: str | None = None,
        parent_job_id: str | None = None,
        scrape_url: str | None = None,
        scrape_headers: dict[str, str] | None = None,
        auto_publish: bool = False,
        warnings: list[str] | None = None,
        import_origin: str | None = None,
        number: int | None = None,
        user_edited: bool = False,
        extra: dict | None = None,
    ) -> JobRecord:
        builder = (
            JobRecordBuilder()
            .with_id(job_id)
            .with_status(status)
            .with_type(job_type)
            .with_preview(preview)
            .with_error(error)
            .with_product_url(product_url)
            .with_folder_label(folder_label)
            .with_source_job_id(source_job_id)
            .with_parent_job_id(parent_job_id)
            .with_scrape(scrape_url, scrape_headers)
            .with_auto_publish(auto_publish)
            .with_warnings(warnings)
            .with_import_origin(import_origin)
        )
        if created_at is not None:
            builder.with_created_at(created_at)
        else:
            builder.with_created_at(datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc))
        if number is not None:
            builder.with_number(number)
        if user_edited:
            builder.with_user_edited(True)
        if extra is not None:
            builder.with_extra(extra)
        return builder.build()
