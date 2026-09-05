"""TDD: thumbnail catalog + on-demand low-res renderer."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from src.export.thumbnail import ThumbnailCatalog, ThumbnailPolicy, ThumbnailRenderer


def _write_jpeg(path: Path, *, width: int, height: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), color=(40, 80, 120)).save(
        path, format="JPEG", quality=90
    )


class _FakeStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.put_calls: list[str] = []

    def ensure_local_root(self, job_id: str) -> Path:
        del job_id
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def ensure_artifact_file(self, job_id: str, relpath: str) -> Path:
        del job_id
        path = self.root / relpath
        if not path.is_file():
            raise FileNotFoundError(relpath)
        return path

    def put_album_file(
        self,
        job_id: str,
        relpath: str,
        path: Path,
        mtime: float | None = None,
    ) -> None:
        del job_id, path, mtime
        self.put_calls.append(relpath)


class TestThumbnailCatalog:
    def test_prefers_tn_thumbnail_not_hrimages(self, tmp_path: Path) -> None:
        _write_jpeg(tmp_path / "hrimages" / "20120802_01hr.JPG", width=2000, height=1500)
        _write_jpeg(tmp_path / "thumbnails" / "TN_20120802_01.JPG", width=160, height=120)
        catalog = ThumbnailCatalog()
        assert catalog.resolve(tmp_path, "20120802_01") == "thumbnails/TN_20120802_01.JPG"

    def test_does_not_use_hrimages_as_thumb(self, tmp_path: Path) -> None:
        _write_jpeg(tmp_path / "hrimages" / "20120802_01hr.JPG", width=2000, height=1500)
        assert ThumbnailCatalog().resolve(tmp_path, "20120802_01") is None

    def test_derived_cache_wins(self, tmp_path: Path) -> None:
        policy = ThumbnailPolicy()
        derived = tmp_path / policy.derived_relpath("20120802_01")
        _write_jpeg(derived, width=100, height=80)
        assert (
            ThumbnailCatalog(policy).resolve(tmp_path, "20120802_01")
            == policy.derived_relpath("20120802_01")
        )


class TestThumbnailRenderer:
    def test_uses_existing_catalog_thumb(self, tmp_path: Path) -> None:
        store = _FakeStore(tmp_path)
        _write_jpeg(tmp_path / "thumbnails" / "TN_a.JPG", width=120, height=90)
        _write_jpeg(tmp_path / "hrimages" / "ahr.JPG", width=2000, height=1500)
        path = ThumbnailRenderer(store).ensure_thumb(
            "job-1",
            item_id="a",
            original_relpath="hrimages/ahr.JPG",
            thumb_relpath="thumbnails/TN_a.JPG",
        )
        assert path.name == "TN_a.JPG"
        assert store.put_calls == []

    def test_synthesizes_and_caches_derived_jpeg(self, tmp_path: Path) -> None:
        store = _FakeStore(tmp_path)
        original = tmp_path / "hrimages" / "20120802_01hr.JPG"
        _write_jpeg(original, width=1600, height=1200)
        renderer = ThumbnailRenderer(store, policy=ThumbnailPolicy(max_edge_px=320))
        first = renderer.ensure_thumb(
            "job-1",
            item_id="20120802_01",
            original_relpath="hrimages/20120802_01hr.JPG",
        )
        with Image.open(first) as image:
            assert max(image.size) <= 320
        assert first.stat().st_size < original.stat().st_size
        assert store.put_calls
        second = renderer.ensure_thumb(
            "job-1",
            item_id="20120802_01",
            original_relpath="hrimages/20120802_01hr.JPG",
        )
        assert second == first

    def test_non_image_original_raises_without_catalog(self, tmp_path: Path) -> None:
        store = _FakeStore(tmp_path)
        video = tmp_path / "hrimages" / "clip01hr.wmv"
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"WMV-only")
        with pytest.raises(FileNotFoundError):
            ThumbnailRenderer(store).ensure_thumb(
                "job-1",
                item_id="clip01",
                original_relpath="hrimages/clip01hr.wmv",
            )
