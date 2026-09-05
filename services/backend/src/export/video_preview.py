"""Local poster + browser-playable mp4 copies for video preview items."""
from __future__ import annotations

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


class _AlbumFileStore(Protocol):
    def put_album_file(
        self,
        job_id: str,
        relpath: str,
        path: Path,
        mtime: Optional[float] = None,
    ) -> None:
        ...


def transcode_to_mp4(source: Path, dest: Path) -> bool:
    """Write ``dest`` as mp4. Returns False on failure (never raises)."""
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


def extract_poster_frame(source: Path, dest: Path) -> bool:
    """Save the first frame of ``source`` as JPEG. Returns False on failure."""
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


def ensure_local_video_previews(
    root: Path,
    *,
    transcode: Optional[TranscodeFn] = None,
    extract_frame: Optional[ExtractFrameFn] = None,
) -> Tuple[str, ...]:
    """Create missing ``thumbnails/TN_{id}.jpg`` and ``preview/{id}.mp4`` sidecars.

    Returns album-relative paths created this call. Failures are ignored so
    folder import / scrape can still finish.
    """
    root = Path(root)
    hr_dir = root / "hrimages"
    if not hr_dir.is_dir():
        return ()
    transcode_fn = transcode or transcode_to_mp4
    extract_fn = extract_frame or extract_poster_frame
    created: list[str] = []
    for path in list(hr_dir.iterdir()):
        if not path.is_file() or not is_video_filename(path.name):
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
    "persist_video_preview_sidecars",
    "transcode_to_mp4",
]
