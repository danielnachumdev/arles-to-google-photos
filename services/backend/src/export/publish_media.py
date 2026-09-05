"""Prepare local media paths that Google Photos can accept on upload."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

from .media_kinds import KIND_VIDEO, infer_item_kind, is_video_filename
from .preview import PreviewItem
from .video_preview import transcode_to_mp4

PathResolver = Callable[[str], Path]
TranscodeFn = Callable[[Path, Path], bool]


class PublishMediaPreparer:
    """Resolve upload bytes for one preview item.

    Non-MP4 videos must become a real (non-empty) ``.mp4`` before
    ``gp_wrapper`` / Photos see them. On Cloud Run, ``play_relpath`` often
    exists as a 0-byte sparse placeholder — this class hydrates it via
    ``resolve`` instead of copying emptiness into the sibling companion.
    """

    def __init__(self, *, transcode: Optional[TranscodeFn] = None) -> None:
        self._transcode = transcode or transcode_to_mp4

    def prepare(
        self,
        item: PreviewItem,
        *,
        root: Path,
        resolve: PathResolver,
    ) -> Path:
        del root  # resolve owns durable hydrate; root is for call-site clarity
        source = resolve(item.relpath)
        if not source.is_file() or source.stat().st_size <= 0:
            raise FileNotFoundError(
                f"Could not load photo '{item.id}' for Google Photos upload "
                f"({item.relpath}). File missing or empty on the server."
            )
        if not self._needs_mp4_companion(item, source):
            return source
        return self._prepare_video_mp4(item, source, resolve=resolve)

    def _needs_mp4_companion(self, item: PreviewItem, source: Path) -> bool:
        if source.suffix.lower() == ".mp4":
            return False
        kind = infer_item_kind(item.relpath, item.kind)
        return kind == KIND_VIDEO or is_video_filename(source.name)

    def _prepare_video_mp4(
        self,
        item: PreviewItem,
        source: Path,
        *,
        resolve: PathResolver,
    ) -> Path:
        companion = source.with_suffix(".mp4")
        self._discard_empty(companion)

        if companion.is_file() and companion.stat().st_size > 0:
            return companion

        play = (item.play_relpath or "").strip()
        if play:
            play_path = resolve(play)
            if play_path.is_file() and play_path.stat().st_size > 0:
                try:
                    shutil.copy2(play_path, companion)
                except OSError as exc:
                    raise RuntimeError(
                        f"Could not prepare MP4 for Google Photos upload of "
                        f"'{item.id}' ({item.relpath}): failed to copy "
                        f"preview '{play}': {exc}"
                    ) from exc
                if companion.is_file() and companion.stat().st_size > 0:
                    return companion

        if self._transcode(source, companion):
            if companion.is_file() and companion.stat().st_size > 0:
                return companion

        raise RuntimeError(
            f"Could not prepare an MP4 for Google Photos upload of '{item.id}' "
            f"({item.relpath}). Convert the video locally or reprocess so a "
            f"preview MP4 exists, then retry publish."
        )

    @staticmethod
    def _discard_empty(path: Path) -> None:
        if path.is_file() and path.stat().st_size <= 0:
            try:
                path.unlink()
            except OSError:
                pass
