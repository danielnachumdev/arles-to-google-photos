"""TDD: album path classifier (structure vs media)."""
from __future__ import annotations

import pytest

from src.jobs.persistence.album_paths import AlbumArtifactClassifier, ArtifactKind


class TestAlbumArtifactClassifier:
    def setup_method(self) -> None:
        self.classifier = AlbumArtifactClassifier()

    @pytest.mark.parametrize(
        "relpath,kind",
        [
            ("index.html", ArtifactKind.STRUCTURE),
            ("index2.html", ArtifactKind.STRUCTURE),
            ("imagepages/20120802_01.html", ArtifactKind.STRUCTURE),
            ("index.css", ArtifactKind.STRUCTURE),
            ("hrimages/20120802_01hr.JPG", ArtifactKind.MEDIA),
            ("thumbnails/TN_20120802_01.JPG", ArtifactKind.MEDIA),
            ("preview/clip01.mp4", ArtifactKind.MEDIA),
            ("icons/home.gif", ArtifactKind.MEDIA),
            ("job.json", ArtifactKind.STATE),
            ("arles-media-index.json", ArtifactKind.STATE),
            ("readme.txt", ArtifactKind.OTHER),
        ],
    )
    def test_classify(self, relpath: str, kind: ArtifactKind) -> None:
        assert self.classifier.classify(relpath) is kind

    def test_retain_locally_only_structure(self) -> None:
        assert self.classifier.retain_locally_after_remote_put("index.html")
        assert not self.classifier.retain_locally_after_remote_put(
            "hrimages/a.jpg"
        )
