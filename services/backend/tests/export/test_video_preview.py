"""TDD: local video poster + mp4 preview sidecars without a real encode."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.export.video_preview import ensure_local_video_previews
from tests.support.suites import VideoPreviewSuite


class TestLocalVideoPreviews(VideoPreviewSuite):
    def test_ensure_local_video_previews_writes_poster_and_mp4(self) -> None:
        self.hr.mkdir()
        source = self.hr / "clip01hr.wmv"
        source.write_bytes(b"WMV-bytes")

        def fake_extract(src: Path, dest: Path) -> bool:
            assert src == source
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\xff\xd8frame\xff\xd9")
            return True

        def fake_transcode(src: Path, dest: Path) -> bool:
            assert src == source
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"ftyp-fake")
            return True

        ensure_local_video_previews(
            self.tmp_path, transcode=fake_transcode, extract_frame=fake_extract
        )

        assert (self.tmp_path / "thumbnails" / "TN_clip01.jpg").read_bytes() == (
            b"\xff\xd8frame\xff\xd9"
        )
        assert (self.tmp_path / "preview" / "clip01.mp4").read_bytes() == b"ftyp-fake"

    def test_ensure_local_video_previews_skips_when_sidecars_exist(self) -> None:
        thumbs = self.tmp_path / "thumbnails"
        preview = self.tmp_path / "preview"
        self.hr.mkdir()
        thumbs.mkdir()
        preview.mkdir()
        (self.hr / "clip01hr.wmv").write_bytes(b"WMV-bytes")
        (thumbs / "TN_clip01.jpg").write_bytes(b"existing-poster")
        (preview / "clip01.mp4").write_bytes(b"existing-mp4")
        calls: list[str] = []

        def boom(src: Path, dest: Path) -> bool:
            del src, dest
            calls.append("called")
            return False

        ensure_local_video_previews(
            self.tmp_path, transcode=boom, extract_frame=boom
        )

        assert calls == []
        assert (thumbs / "TN_clip01.jpg").read_bytes() == b"existing-poster"
        assert (preview / "clip01.mp4").read_bytes() == b"existing-mp4"

    def test_ensure_local_video_previews_ignores_transcode_failure(self) -> None:
        self.hr.mkdir()
        (self.hr / "clip01hr.wmv").write_bytes(b"WMV-bytes")

        ensure_local_video_previews(
            self.tmp_path,
            transcode=lambda src, dest: False,
            extract_frame=lambda src, dest: False,
        )

        assert not (self.tmp_path / "thumbnails" / "TN_clip01.jpg").is_file()
        assert not (self.tmp_path / "preview" / "clip01.mp4").is_file()

    def test_ensure_skips_when_hrimages_missing(self) -> None:
        ensure_local_video_previews(self.tmp_path)
        assert not (self.tmp_path / "thumbnails").exists()

    def test_ensure_skips_browser_playable_transcode(self) -> None:
        self.hr.mkdir()
        (self.hr / "clip01hr.mp4").write_bytes(b"ftyp")
        calls: list[str] = []

        def extract(src: Path, dest: Path) -> bool:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\xff\xd8\xff\xd9")
            calls.append("extract")
            return True

        def transcode(src: Path, dest: Path) -> bool:
            del src, dest
            calls.append("transcode")
            return True

        ensure_local_video_previews(
            self.tmp_path, transcode=transcode, extract_frame=extract
        )
        assert "extract" in calls
        assert "transcode" not in calls

    def test_ensure_uses_hr_image_sidecar_instead_of_extract(self) -> None:
        self.hr.mkdir()
        (self.hr / "clip01hr.wmv").write_bytes(b"WMV")
        (self.hr / "clip01hr.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        calls: list[str] = []

        def boom(src: Path, dest: Path) -> bool:
            del src, dest
            calls.append("called")
            return False

        ensure_local_video_previews(
            self.tmp_path, transcode=lambda s, d: True, extract_frame=boom
        )
        assert "called" not in calls

    def test_transcode_and_extract_moviepy_paths(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys
        import types

        from src.export.video_preview import extract_poster_frame, transcode_to_mp4

        source = self.tmp_path / "in.wmv"
        source.write_bytes(b"wmv")

        class FakeClip:
            def write_videofile(
                self, path: str, verbose: bool = False, logger: object = None
            ) -> None:
                del verbose, logger
                Path(path).write_bytes(b"mp4")

            def save_frame(self, path: str, t: float = 0) -> None:
                del t
                Path(path).write_bytes(b"\xff\xd8\xff\xd9")

            def close(self) -> None:
                return None

        editor = types.ModuleType("moviepy.editor")
        editor.VideoFileClip = lambda _path: FakeClip()  # type: ignore[attr-defined]
        pkg = types.ModuleType("moviepy")
        pkg.editor = editor  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "moviepy", pkg)
        monkeypatch.setitem(sys.modules, "moviepy.editor", editor)
        dest_mp4 = self.tmp_path / "out.mp4"
        dest_jpg = self.tmp_path / "out.jpg"
        assert transcode_to_mp4(source, dest_mp4) is True
        assert dest_mp4.read_bytes() == b"mp4"
        assert extract_poster_frame(source, dest_jpg) is True
        assert dest_jpg.read_bytes().startswith(b"\xff\xd8")

    def test_transcode_returns_false_when_moviepy_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import builtins

        from src.export.video_preview import extract_poster_frame, transcode_to_mp4

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object):
            if name == "moviepy.editor" or name.startswith("moviepy"):
                raise ImportError("no moviepy")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert transcode_to_mp4(self.tmp_path / "a.wmv", self.tmp_path / "b.mp4") is False
        assert extract_poster_frame(self.tmp_path / "a.wmv", self.tmp_path / "b.jpg") is False
