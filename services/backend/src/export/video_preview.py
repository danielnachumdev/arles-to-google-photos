"""Local poster + browser-playable mp4 copies for video preview items."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional, Protocol, Sequence, Tuple

from .media_kinds import (
    BROWSER_PLAYABLE_VIDEO,
    IMAGE_EXTENSIONS,
    id_from_hr_stem,
    is_video_filename,
)

TranscodeFn = Callable[[Path, Path], bool]
ExtractFrameFn = Callable[[Path, Path], bool]
EnsureFileFn = Callable[[str], Path]

# Folders that may hold gallery source videos (not generated preview/).
_SOURCE_VIDEO_DIRS = ("hrimages", "images", "imagepages")


class _AlbumFileStore(Protocol):
    def put_album_file(
        self,
        job_id: str,
        relpath: str,
        path: Path,
        mtime: Optional[float] = None,
    ) -> None:
        ...


def _ffmpeg_exe() -> Optional[str]:
    try:
        import imageio_ffmpeg
    except ImportError:
        return None
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def transcode_to_mp4(source: Path, dest: Path) -> bool:
    """Write ``dest`` as mp4. Returns False on failure (never raises)."""
    if _transcode_with_ffmpeg(source, dest):
        return True
    return _transcode_with_moviepy(source, dest)


def extract_poster_frame(source: Path, dest: Path) -> bool:
    """Save the first frame of ``source`` as JPEG. Returns False on failure."""
    if _extract_frame_with_ffmpeg(source, dest):
        return True
    return _extract_frame_with_moviepy(source, dest)


def _transcode_with_ffmpeg(source: Path, dest: Path) -> bool:
    ffmpeg = _ffmpeg_exe()
    if not ffmpeg:
        return False
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{dest.stem}_xcode_",
            suffix=".mp4",
            dir=str(dest.parent),
            delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
        # Remux first (MOV→MP4); re-encode for WMV / incompatible codecs.
        for args in (
            [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(tmp_path),
            ],
            [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(tmp_path),
            ],
        ):
            result = subprocess.run(args, check=False, capture_output=True)
            if (
                result.returncode == 0
                and tmp_path.is_file()
                and tmp_path.stat().st_size > 0
            ):
                tmp_path.replace(dest)
                return True
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        return False
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        return False


def _extract_frame_with_ffmpeg(source: Path, dest: Path) -> bool:
    ffmpeg = _ffmpeg_exe()
    if not ffmpeg:
        return False
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-ss",
                "0",
                "-vframes",
                "1",
                str(dest),
            ],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0 and dest.is_file() and dest.stat().st_size > 0
    except Exception:
        return False


def _transcode_with_moviepy(source: Path, dest: Path) -> bool:
    try:
        import moviepy.editor as moviepy  # type: ignore[import-untyped]
    except Exception:
        return False
    try:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        clip = moviepy.VideoFileClip(str(source))
        try:
            clip.write_videofile(str(dest), verbose=False, logger=None)
        finally:
            close = getattr(clip, "close", None)
            if callable(close):
                close()
        return dest.is_file() and dest.stat().st_size > 0
    except Exception:
        return False


def _extract_frame_with_moviepy(source: Path, dest: Path) -> bool:
    try:
        import moviepy.editor as moviepy  # type: ignore[import-untyped]
    except Exception:
        return False
    try:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        clip = moviepy.VideoFileClip(str(source))
        try:
            clip.save_frame(str(dest), t=0)
        finally:
            close = getattr(clip, "close", None)
            if callable(close):
                close()
        return dest.is_file() and dest.stat().st_size > 0
    except Exception:
        return False


def iter_video_source_relpaths(root: Path) -> Tuple[str, ...]:
    """Album-relative paths of source videos that may need preview sidecars."""
    root = Path(root)
    found: list[str] = []
    for folder_name in _SOURCE_VIDEO_DIRS:
        folder = root / folder_name
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file() or not is_video_filename(path.name):
                continue
            found.append(path.relative_to(root).as_posix())
    return tuple(found)


def hydrate_video_sources(root: Path, ensure_file: EnsureFileFn) -> None:
    """Download real video bytes for sparse/GCS placeholders before transcode.

    Cloud Run keeps empty media placeholders until ``ensure_file``; moviepy/ffmpeg
    cannot build ``preview/*.mp4`` from zero-byte WMV stubs. Also re-hydrates
    existing ``preview/*.mp4`` sidecars so reprocess does not re-encode needlessly.
    """
    for rel in iter_video_source_relpaths(root):
        try:
            ensure_file(rel)
        except Exception:
            # Missing object or network blip — skip; ensure_local will ignore empty.
            pass
    preview_dir = Path(root) / "preview"
    if not preview_dir.is_dir():
        return
    for path in preview_dir.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in BROWSER_PLAYABLE_VIDEO:
            continue
        if path.stat().st_size > 0:
            continue
        try:
            ensure_file(path.relative_to(root).as_posix())
        except Exception:
            pass


def ensure_local_video_previews(
    root: Path,
    *,
    transcode: Optional[TranscodeFn] = None,
    extract_frame: Optional[ExtractFrameFn] = None,
) -> Tuple[str, ...]:
    """Create missing ``thumbnails/TN_{id}.jpg`` and ``preview/{id}.mp4`` sidecars.

    Returns album-relative paths created this call. Failures are ignored so
    folder import / scrape can still finish. Zero-byte sources (GCS placeholders)
    are skipped — call :func:`hydrate_video_sources` first on cloud backends.
    """
    root = Path(root)
    transcode_fn = transcode or transcode_to_mp4
    extract_fn = extract_frame or extract_poster_frame
    created: list[str] = []
    for rel in iter_video_source_relpaths(root):
        path = root / rel
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        item_id = id_from_hr_stem(path.stem)
        if not _has_image_sidecar(root, item_id):
            dest = root / "thumbnails" / f"TN_{item_id}.jpg"
            if extract_fn(path, dest):
                created.append(dest.relative_to(root).as_posix())
        if path.suffix.lower() in BROWSER_PLAYABLE_VIDEO:
            continue
        play_dest = root / "preview" / f"{item_id}.mp4"
        if play_dest.is_file() and play_dest.stat().st_size > 0:
            continue
        if transcode_fn(path, play_dest):
            created.append(play_dest.relative_to(root).as_posix())
    return tuple(created)


def persist_video_preview_sidecars(
    store: _AlbumFileStore,
    job_id: str,
    root: Path,
    relpaths: Sequence[str],
) -> None:
    """Best-effort durable upload of newly created video preview sidecars."""
    root = Path(root)
    for rel in relpaths:
        safe = (rel or "").replace("\\", "/").lstrip("/")
        if not safe or safe.startswith("..") or "/../" in f"/{safe}/":
            continue
        path = root / safe
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        try:
            store.put_album_file(job_id, safe, path)
        except Exception:
            # Local sidecar is enough for this process; durable put is best-effort.
            pass


def _has_image_sidecar(root: Path, item_id: str) -> bool:
    key = item_id.casefold()
    for folder, stem_fn in (
        (root / "thumbnails", _thumb_stem_id),
        (root / "preview", lambda stem: stem),
        (root / "hrimages", id_from_hr_stem),
    ):
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if stem_fn(path.stem).casefold() == key:
                return True
    return False


def _thumb_stem_id(stem: str) -> str:
    if len(stem) > 3 and stem[:3].casefold() == "tn_":
        return stem[3:]
    return stem


__all__ = [
    "ensure_local_video_previews",
    "extract_poster_frame",
    "hydrate_video_sources",
    "iter_video_source_relpaths",
    "persist_video_preview_sidecars",
    "transcode_to_mp4",
]
