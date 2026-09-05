"""TDD: sparse album workspace + media index for Cloud Run scratch pads."""
from __future__ import annotations

from pathlib import Path

from src.export.media_index import MEDIA_INDEX_NAME, MediaIndex, MediaIndexEntry
from src.export.parser import AlbumExportParser
from src.jobs.persistence.sparse_cache import SparseAlbumWorkspace
from tests.conftest import DAY1_MINI


class TestMediaIndex:
    def test_roundtrip_json(self, tmp_path: Path) -> None:
        index = MediaIndex(
            {
                "hrimages/a.jpg": MediaIndexEntry(size_bytes=12, mtime=100.0),
            }
        )
        index.write(tmp_path)
        loaded = MediaIndex.read(tmp_path)
        entry = loaded.get("hrimages/a.jpg")
        assert entry is not None
        assert entry.size_bytes == 12
        assert entry.mtime == 100.0


class TestSparseAlbumWorkspace:
    def test_parser_reads_placeholders_via_media_index(self, tmp_path: Path) -> None:
        from src.export.media_index import clear_media_index_cache

        clear_media_index_cache()
        root = tmp_path / "album"
        workspace = SparseAlbumWorkspace(root)
        for rel in ("index.html", "imagepages/20120802_01.html"):
            workspace.place_structure_file(rel, (DAY1_MINI / rel).read_bytes())
        jpeg = (DAY1_MINI / "hrimages" / "20120802_01hr.JPG").read_bytes()
        rel = "hrimages/20120802_01hr.JPG"
        workspace.place_media_placeholder(
            rel, size_bytes=len(jpeg), mtime=1_344_000_000.0
        )
        workspace.write_media_index(
            MediaIndex(
                {rel: MediaIndexEntry(size_bytes=len(jpeg), mtime=1_344_000_000.0)}
            )
        )

        assert (root / rel).stat().st_size == 0
        assert (root / MEDIA_INDEX_NAME).is_file()

        preview = AlbumExportParser().parse(root)
        assert preview.title == "2/8/2012 - mini fixture"
        assert len(preview.items) == 1
        assert preview.items[0].id == "20120802_01"
        assert preview.items[0].size_bytes == len(jpeg)

    def test_discard_media_bodies_keeps_structure(self, tmp_path: Path) -> None:
        root = tmp_path / "album"
        workspace = SparseAlbumWorkspace(root)
        workspace.place_structure_file("index.html", b"<html/>")
        (root / "hrimages").mkdir(parents=True, exist_ok=True)
        (root / "hrimages" / "a.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        workspace.discard_media_bodies(["index.html", "hrimages/a.jpg"])
        assert (root / "index.html").is_file()
        assert not (root / "hrimages" / "a.jpg").exists()
