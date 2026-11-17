"""Streamed Google Photos upload helpers."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.export.photos_upload import (
    content_type_for_path,
    release_upload_paths,
    sparse_local_file,
    stream_upload_media,
)


class TestPhotosUpload:
    def test_content_type_for_common_suffixes(self) -> None:
        assert content_type_for_path(Path("a.JPG")) == "image/jpeg"
        assert content_type_for_path(Path("a.mp4")) == "video/mp4"
        assert content_type_for_path(Path("a.mov")) == "video/quicktime"

    def test_stream_upload_media_posts_file_handle_not_bytes(self, tmp_path: Path) -> None:
        media = tmp_path / "clip.mp4"
        media.write_bytes(b"ftyp" + (b"x" * 4096))
        gp = MagicMock()
        response = MagicMock()
        response.content = b"upload-token-1"
        response.raise_for_status = MagicMock()
        gp.request.return_value = response

        token = stream_upload_media(gp, media)

        assert token == "upload-token-1"
        kwargs = gp.request.call_args.kwargs
        assert kwargs["data"] is not None
        # Must not pass a fully-buffered bytes payload.
        assert not isinstance(kwargs["data"], (bytes, bytearray))
        headers = kwargs["additional_headers"]
        assert headers["X-Goog-Upload-Protocol"] == "raw"
        assert headers["X-Goog-Upload-Content-Type"] == "video/mp4"

    def test_release_upload_paths_sparses_companion(self, tmp_path: Path) -> None:
        src = tmp_path / "hrimages" / "a.MOV"
        companion = tmp_path / "hrimages" / "a.mp4"
        src.parent.mkdir()
        src.write_bytes(b"mov-bytes")
        companion.write_bytes(b"mp4-bytes")
        released: list[str] = []

        release_upload_paths(
            album_root=tmp_path,
            item_relpath="hrimages/a.MOV",
            play_relpath=None,
            upload_path=companion,
            release=released.append,
        )

        assert "hrimages/a.MOV" in released
        assert src.read_bytes() == b""
        assert companion.read_bytes() == b""

    def test_release_upload_paths_noop_without_releaser(self, tmp_path: Path) -> None:
        companion = tmp_path / "a.mp4"
        companion.write_bytes(b"keep-me")
        release_upload_paths(
            album_root=tmp_path,
            item_relpath="a.mp4",
            play_relpath=None,
            upload_path=companion,
            release=None,
        )
        assert companion.read_bytes() == b"keep-me"

    def test_sparse_local_file_is_idempotent(self, tmp_path: Path) -> None:
        path = tmp_path / "gone.bin"
        sparse_local_file(path)
        path.write_bytes(b"data")
        sparse_local_file(path)
        assert path.read_bytes() == b""
