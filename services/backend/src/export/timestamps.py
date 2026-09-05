"""Stamp capture times onto local media before Google Photos upload."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Optional, Sequence

import piexif
from gp_wrapper.utils import FileTime, FileTimeService

from .media_kinds import is_video_filename
from .preview import PreviewItem

_JPEG_SUFFIXES = {".jpg", ".jpeg", ".jpe"}
_EXIF_FMT = "%Y:%m:%d %H:%M:%S"
_MP4_CREATION_FMT = "%Y-%m-%dT%H:%M:%S.000000Z"


class CaptureTimestampStamper:
    """Write taken_on + gallery order onto filesystem times, JPEG EXIF, and video metadata."""

    def __init__(self, times: Optional[FileTimeService] = None) -> None:
        self._times = times or FileTimeService()

    def stamp_upload(
        self,
        root: Path,
        items: Sequence[PreviewItem],
        *,
        resolve: Optional[Callable[[str], Path]] = None,
    ) -> None:
        prev: Optional[datetime] = None
        root = Path(root)
        resolve_path = resolve or (lambda rel: root / Path(rel))
        album_day = self._album_day(root, items, resolve=resolve_path)
        for index, item in enumerate(items):
            path = resolve_path(item.relpath)
            if not path.is_file():
                continue
            stamp = self._resolve_stamp(path, item.taken_on, index, prev, album_day)
            if stamp is None:
                continue
            self._write(path, stamp, root=root, item=item)
            prev = stamp

    def stamp_path(
        self,
        path: Path,
        item: PreviewItem,
        *,
        index: int,
        prev: Optional[datetime],
        album_day: Optional[date],
        root: Path,
    ) -> Optional[datetime]:
        """Stamp one media file; returns the stamp used (for ordering)."""
        path = Path(path)
        if not path.is_file():
            return prev
        stamp = self._resolve_stamp(path, item.taken_on, index, prev, album_day)
        if stamp is None:
            return prev
        self._write(path, stamp, root=root, item=item)
        return stamp

    def album_day_for(
        self,
        root: Path,
        items: Sequence[PreviewItem],
        *,
        resolve: Optional[Callable[[str], Path]] = None,
    ) -> Optional[date]:
        resolve_path = resolve or (lambda rel: Path(root) / rel)
        return self._album_day(root, items, resolve=resolve_path)

    def _album_day(
        self,
        root: Path,
        items: Sequence[PreviewItem],
        *,
        resolve: Optional[Callable[[str], Path]] = None,
    ) -> Optional[date]:
        resolve_path = resolve or (lambda rel: Path(root) / rel)
        for item in items:
            if item.taken_on is not None:
                return item.taken_on
        for item in items:
            path = resolve_path(item.relpath)
            if not path.is_file() or path.stat().st_size <= 0:
                continue
            exif = self._read_exif(path)
            if exif is not None:
                return exif.date()
        return None

    def _resolve_stamp(
        self,
        path: Path,
        taken_on: Optional[date],
        index: int,
        prev: Optional[datetime],
        album_day: Optional[date],
    ) -> Optional[datetime]:
        stamp = self._read_exif(path)
        if stamp is None:
            day = taken_on if taken_on is not None else album_day
            if day is not None:
                stamp = datetime.combine(day, time.min) + timedelta(seconds=index)
        if stamp is None and prev is not None:
            stamp = prev + timedelta(seconds=1)
        if stamp is None:
            return None
        if prev is not None and stamp <= prev:
            stamp = prev + timedelta(seconds=1)
        return stamp.replace(microsecond=0)

    def _read_exif(self, path: Path) -> Optional[datetime]:
        if path.suffix.lower() not in _JPEG_SUFFIXES:
            return None
        try:
            exif = piexif.load(str(path))
        except Exception:
            return None
        raw = exif.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
        if not raw:
            raw = exif.get("0th", {}).get(piexif.ImageIFD.DateTime)
        return _parse_exif_datetime(raw)

    def _write(
        self,
        path: Path,
        stamp: datetime,
        *,
        root: Path,
        item: PreviewItem,
    ) -> None:
        if path.suffix.lower() in _JPEG_SUFFIXES:
            self._write_jpeg_exif(path, stamp)
        self._times.set(
            str(path),
            FileTime(access=stamp, modification=stamp),
        )
        if is_video_filename(path.name):
            self._write_video_capture_time(path, stamp, root=root, item=item)

    def _write_jpeg_exif(self, path: Path, stamp: datetime) -> None:
        try:
            try:
                exif = piexif.load(str(path))
            except Exception:
                exif = {
                    "0th": {},
                    "Exif": {},
                    "GPS": {},
                    "1st": {},
                    "thumbnail": None,
                }
            encoded = stamp.strftime(_EXIF_FMT).encode("ascii")
            exif.setdefault("0th", {})[piexif.ImageIFD.DateTime] = encoded
            exif.setdefault("Exif", {})[piexif.ExifIFD.DateTimeOriginal] = encoded
            exif.setdefault("Exif", {})[piexif.ExifIFD.DateTimeDigitized] = encoded
            piexif.insert(piexif.dump(exif), str(path))
        except Exception:
            return

    def _write_video_capture_time(
        self,
        path: Path,
        stamp: datetime,
        *,
        root: Path,
        item: PreviewItem,
    ) -> None:
        """Embed creation_time in the MP4 bytes Google Photos actually uploads.

        Filesystem mtime is not part of the upload payload. ``gp_wrapper`` converts
        non-MP4 videos (``.mov`` / ``.wmv``) to ``{stem}.mp4`` at upload time when
        that companion is missing — and moviepy's new file gets *today* as
        creation_time. Prepare (or reuse) that companion here and stamp it.
        """
        target = self._video_metadata_target(path, root=root, item=item)
        if target is None:
            return
        if not self._embed_mp4_creation_time(target, stamp):
            return
        self._times.set(
            str(target),
            FileTime(access=stamp, modification=stamp),
        )

    def _video_metadata_target(
        self,
        path: Path,
        *,
        root: Path,
        item: PreviewItem,
    ) -> Optional[Path]:
        if path.suffix.lower() == ".mp4":
            return path
        companion = path.with_suffix(".mp4")
        if companion.is_file() and companion.stat().st_size > 0:
            return companion
        play = item.play_relpath
        if play:
            play_path = root / play
            if play_path.is_file():
                try:
                    shutil.copy2(play_path, companion)
                except OSError:
                    return None
                return companion
        if self._transcode_to_mp4(path, companion):
            return companion
        return None

    def _transcode_to_mp4(self, source: Path, dest: Path) -> bool:
        """Create the ``.mp4`` companion ``gp_wrapper.upload_media`` will prefer."""
        try:
            import imageio_ffmpeg
        except ImportError:
            return False
        try:
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return False
        parent = dest.parent
        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{dest.stem}_xcode_",
                suffix=".mp4",
                dir=str(parent),
                delete=False,
            ) as handle:
                tmp_path = Path(handle.name)
            # Prefer remux when the container allows it (typical for MOV→MP4).
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
                result = subprocess.run(
                    args,
                    check=False,
                    capture_output=True,
                )
                if result.returncode == 0 and tmp_path.is_file() and tmp_path.stat().st_size > 0:
                    tmp_path.replace(dest)
                    return True
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            return False
        except Exception:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            return False

    def _embed_mp4_creation_time(self, path: Path, stamp: datetime) -> bool:
        try:
            import imageio_ffmpeg
        except ImportError:
            return False
        try:
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return False
        encoded = stamp.strftime(_MP4_CREATION_FMT)
        parent = path.parent
        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{path.stem}_stamp_",
                suffix=path.suffix,
                dir=str(parent),
                delete=False,
            ) as handle:
                tmp_path = Path(handle.name)
            result = subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(path),
                    "-c",
                    "copy",
                    "-map_metadata",
                    "0",
                    "-metadata",
                    f"creation_time={encoded}",
                    str(tmp_path),
                ],
                check=False,
                capture_output=True,
            )
            if result.returncode != 0:
                tmp_path.unlink(missing_ok=True)
                return False
            tmp_path.replace(path)
            return True
        except Exception:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            return False


def _parse_exif_datetime(raw: object) -> Optional[datetime]:
    if raw is None:
        return None
    text = raw.decode("ascii") if isinstance(raw, bytes) else str(raw)
    try:
        return datetime.strptime(text, _EXIF_FMT)
    except ValueError:
        return None
