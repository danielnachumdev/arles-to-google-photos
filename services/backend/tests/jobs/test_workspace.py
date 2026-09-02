"""JobWorkspace: write uploaded album trees and apply FileTimeService timestamps."""
from datetime import datetime

import pytest
from gp_wrapper.utils import FileTimeService

from tests.support.suites import WorkspaceSuite


class TestJobWorkspace(WorkspaceSuite):
    def test_materialize_writes_nested_relpaths(self) -> None:
        returned = self.workspace.materialize(
            [
                ("hrimages/a.jpg", self.JPEG_BYTES, None),
                ("index.html", self.HTML_BYTES, None),
            ]
        )

        assert returned == self.root
        assert (self.root / "hrimages" / "a.jpg").read_bytes() == self.JPEG_BYTES
        assert (self.root / "index.html").read_bytes() == self.HTML_BYTES

    def test_materialize_accepts_backslash_relpaths(self) -> None:
        self.workspace.materialize(
            [
                (r"hrimages\a.jpg", self.JPEG_BYTES, None),
                (r"imagepages\20120802_01.html", self.HTML_BYTES, None),
            ]
        )

        assert (self.root / "hrimages" / "a.jpg").read_bytes() == self.JPEG_BYTES
        assert (self.root / "imagepages" / "20120802_01.html").read_bytes() == self.HTML_BYTES

    def test_materialize_applies_last_modified_via_file_time_service(self) -> None:
        stamp = datetime(2012, 8, 2, 12, 0, 0).timestamp()
        self.workspace.materialize([("hrimages/a.jpg", self.JPEG_BYTES, stamp)])

        got = FileTimeService().get(str(self.root / "hrimages" / "a.jpg"))
        assert got.modification is not None
        assert abs(got.modification.timestamp() - stamp) <= 2
        assert got.access is not None
        assert abs(got.access.timestamp() - stamp) <= 2

    def test_materialize_rejects_path_traversal(self) -> None:
        outside = self.tmp_path / "secret"

        with pytest.raises(ValueError, match="traversal"):
            self.workspace.materialize([("../secret", b"leaked", None)])

        assert not outside.exists()
        assert not (self.tmp_path / "secret").exists()
        assert list(self.root.rglob("*")) == [] or not any(
            p.is_file() and p.read_bytes() == b"leaked" for p in self.root.rglob("*")
        )

    def test_materialize_rejects_backslash_path_traversal(self) -> None:
        with pytest.raises(ValueError, match="traversal"):
            self.workspace.materialize([(r"..\secret", b"leaked", None)])

        assert not (self.tmp_path / "secret").exists()

    def test_materialize_rejects_absolute_relpath(self) -> None:
        with pytest.raises(ValueError, match="traversal"):
            self.workspace.materialize(
                [(str(self.tmp_path / "secret"), b"leaked", None)]
            )
        assert not (self.tmp_path / "secret").exists()

    def test_materialize_creates_parent_directories(self) -> None:
        assert not self.root.exists()
        self.workspace.materialize([("hrimages/nested/a.jpg", self.JPEG_BYTES, None)])

        dest = self.root / "hrimages" / "nested" / "a.jpg"
        assert dest.is_file()
        assert dest.read_bytes() == self.JPEG_BYTES
