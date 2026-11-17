"""Stream media bytes to Google Photos without buffering the whole file in RAM."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from gpsdk.utils import HeaderType, RequestType
from gpsdk.utils import UPLOAD_MEDIA_ITEM_ENDPOINT

_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".jpe": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".wmv": "video/x-ms-wmv",
    ".avi": "video/avi",
    ".mpg": "video/mpeg",
    ".mpeg": "video/mpeg",
}


def content_type_for_path(path: Path) -> str:
    """MIME type for Photos ``X-Goog-Upload-Content-Type``."""
    return _MIME_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")


def stream_upload_media(gp: Any, media: Union[str, Path]) -> str:
    """Upload one local file via the raw Photos upload protocol.

    Passes an open file object as ``data`` so ``requests`` streams the body.
    Peak RAM does not track file size (unlike ``gpsdk.MediaItem.upload_media``,
    which ``read()``s the whole payload into a bytes object).
    """
    path = Path(media)
    if not path.is_file() or path.stat().st_size <= 0:
        raise FileNotFoundError(f"upload source missing or empty: {path}")
    headers = {
        "X-Goog-Upload-Protocol": "raw",
        "X-Goog-Upload-Content-Type": content_type_for_path(path),
    }
    with path.open("rb") as handle:
        response = gp.request(
            RequestType.POST,
            UPLOAD_MEDIA_ITEM_ENDPOINT,
            header_type=HeaderType.OCTET,
            additional_headers=headers,
            data=handle,
        )
    response.raise_for_status()
    token = response.content.decode("utf-8").strip()
    if not token:
        raise RuntimeError("Google Photos upload returned an empty upload token")
    return token


def sparse_local_file(path: Path) -> None:
    """Replace a local file with a 0-byte placeholder (GCS scratch release)."""
    path = Path(path)
    if not path.exists():
        return
    try:
        if path.is_file():
            path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    except OSError:
        pass


def release_upload_paths(
    *,
    album_root: Path,
    item_relpath: str,
    play_relpath: Optional[str],
    upload_path: Path,
    release: Optional[Any] = None,
) -> None:
    """Drop hydrated originals / companions after a successful Photos upload.

    No-op when ``release`` is None (local FS keeps the full album tree).
    """
    if release is None:
        return
    album_root = Path(album_root)
    seen: set[Path] = set()

    def _one(rel_or_path: Union[str, Path]) -> None:
        raw = str(rel_or_path or "").strip()
        if not raw:
            return
        path = Path(raw)
        if not path.is_absolute():
            path = album_root / raw
        path = path.resolve() if path.exists() else path
        if path in seen:
            return
        seen.add(path)
        try:
            rel = path.relative_to(album_root.resolve()).as_posix()
        except Exception:
            sparse_local_file(path)
            return
        release(rel)
        # Companion .mp4 may sit beside the original without an artifact key.
        if path.is_file() and path.stat().st_size > 0:
            sparse_local_file(path)

    _one(item_relpath)
    if play_relpath:
        _one(play_relpath)
    _one(upload_path)
