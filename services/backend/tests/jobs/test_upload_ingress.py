"""TDD: streaming multipart album ingress (no full local staging tree)."""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.jobs.persistence.gcs_artifacts import GcsArtifactStore
from src.jobs.upload_ingress import (
    AlbumUploadPart,
    MultipartAlbumIngress,
    peek_gallery_title_from_parts,
)
from tests.conftest import DAY1_MINI
from tests.support.fakes.gcs import FakeGcsClient


class TestPeekGalleryTitleFromParts:
    def test_reads_only_index_html(self) -> None:
        index = (DAY1_MINI / "index.html").read_bytes()
        parts = [
            AlbumUploadPart("readme.txt", io.BytesIO(b"nope"), None),
            AlbumUploadPart("index.html", io.BytesIO(index), None),
            AlbumUploadPart(
                "hrimages/a.jpg", io.BytesIO(b"\xff\xd8\xff\xd9"), None
            ),
        ]
        title = peek_gallery_title_from_parts(parts)
        assert title == "2/8/2012 - mini fixture"
        # Streams remain readable for a later accept pass.
        assert parts[1].stream.tell() == 0 or parts[1].stream.seek(0) == 0


class TestMultipartAlbumIngress:
    def test_streams_parts_into_gcs_without_full_staging_tree(
        self, tmp_path: Path
    ) -> None:
        gcs = FakeGcsClient()
        artifacts = GcsArtifactStore(
            tmp_path / "cache",
            bucket="b",
            prefix="jobs",
            client=gcs,
        )
        store = MagicMock()
        store.retains_full_local_tree.return_value = False
        store.put_album_file = MagicMock(
            side_effect=lambda job_id, rel, path, mtime=None: artifacts.put_file(
                job_id, rel, Path(path), mtime, owner_id="owner-1"
            )
        )

        ingest = MagicMock()
        ingest.start.return_value = "job-1"
        submitted: list = []

        def submit(job_id: str, fn) -> None:
            submitted.append(job_id)
            fn()

        ingest.finish_prepared.return_value = "job-1"

        ingress = MultipartAlbumIngress(
            store=store,
            ingest=ingest,
            jobs_root=tmp_path,
            submit=submit,
        )

        jpeg = (DAY1_MINI / "hrimages" / "20120802_01hr.JPG").read_bytes()
        index = (DAY1_MINI / "index.html").read_bytes()
        page = (DAY1_MINI / "imagepages" / "20120802_01.html").read_bytes()
        parts = [
            AlbumUploadPart("index.html", io.BytesIO(index), None),
            AlbumUploadPart(
                "hrimages/20120802_01hr.JPG", io.BytesIO(jpeg), 1_344_000_000.0
            ),
            AlbumUploadPart(
                "imagepages/20120802_01.html", io.BytesIO(page), None
            ),
        ]

        job_id = ingress.ingest(
            parts,
            overwrite=False,
            auto_publish=False,
            access_token=None,
            owner_id="owner-1",
        )

        assert job_id == "job-1"
        ingest.start.assert_called_once()
        assert ingest.start.call_args.kwargs["title"] == "2/8/2012 - mini fixture"
        assert store.put_album_file.call_count == 3
        assert submitted == ["job-1"]
        ingest.finish_prepared.assert_called_once_with("job-1", overwrite=False)

        # No leftover staging directory under jobs_root.
        staging_dirs = [
            p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith("arles-upload-")
        ]
        assert staging_dirs == []

        # Durable objects in GCS; local media is placeholder only.
        assert artifacts.exists("job-1", "hrimages/20120802_01hr.JPG", owner_id="owner-1")
        cache_media = tmp_path / "cache" / "job-1" / "hrimages" / "20120802_01hr.JPG"
        assert cache_media.is_file()
        assert cache_media.stat().st_size == 0
        assert (
            artifacts.ensure_file(
                "job-1", "hrimages/20120802_01hr.JPG", owner_id="owner-1"
            ).read_bytes()
            == jpeg
        )

    def test_iter_ingest_yields_store_progress_then_complete(
        self, tmp_path: Path
    ) -> None:
        store = MagicMock()
        ingest = MagicMock()
        ingest.start.return_value = "job-1"
        ingest.finish_prepared.return_value = "job-1"
        emitted: list = []

        def emit(job_id: str, stage: str, message: str = "", **kwargs) -> None:
            emitted.append((job_id, stage, message, kwargs))

        ingress = MultipartAlbumIngress(
            store=store,
            ingest=ingest,
            jobs_root=tmp_path,
            submit=lambda _jid, fn: fn(),
            events_emit=emit,
        )
        parts = [
            AlbumUploadPart("index.html", io.BytesIO(b"<html></html>"), None),
            AlbumUploadPart("a.jpg", io.BytesIO(b"\xff\xd8"), None),
        ]
        events = list(ingress.iter_ingest(parts, owner_id="o"))
        assert [e["event"] for e in events] == ["store", "store", "complete"]
        assert events[0]["current"] == 1 and events[0]["total"] == 2
        assert events[1]["current"] == 2 and events[1]["total"] == 2
        assert events[2]["job_id"] == "job-1"
        assert store.put_album_file.call_count == 2
        assert len(emitted) == 2
        assert emitted[0][0] == "job-1"
        assert emitted[0][2] == "Storing files"
        assert emitted[1][3]["current"] == 2

    def test_album_exists_propagates_before_any_put(self, tmp_path: Path) -> None:
        from src.jobs.ingest import AlbumExistsError

        store = MagicMock()
        ingest = MagicMock()
        ingest.start.side_effect = AlbumExistsError("existing", "Title")
        ingress = MultipartAlbumIngress(
            store=store,
            ingest=ingest,
            jobs_root=tmp_path,
            submit=lambda *_a, **_k: None,
        )
        parts = [
            AlbumUploadPart(
                "index.html",
                io.BytesIO(b'<span class="gallerytitle">Title</span>'),
                None,
            )
        ]
        with pytest.raises(AlbumExistsError):
            ingress.ingest(
                parts,
                overwrite=False,
                auto_publish=False,
                access_token=None,
                owner_id="o",
            )
        store.put_album_file.assert_not_called()
