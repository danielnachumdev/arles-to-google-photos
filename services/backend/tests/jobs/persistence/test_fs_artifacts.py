"""TDD: ArtifactStore filesystem backend (album trees, not job metadata)."""
from __future__ import annotations

from pathlib import Path

from src.jobs.persistence.artifacts import ArtifactStore
from src.jobs.persistence.fs_artifacts import FsArtifactStore
from tests.support.suites import ArtifactStoreSuite


class TestFsArtifactStore(ArtifactStoreSuite):
    def make_store(self, tmp_path: Path) -> ArtifactStore:
        return FsArtifactStore(tmp_path)

    def test_fs_artifact_store_is_artifact_store(self) -> None:
        assert issubclass(FsArtifactStore, ArtifactStore)
