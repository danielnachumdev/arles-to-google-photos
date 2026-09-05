"""Declarative thumbnail resolution and on-demand low-res rendering."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from .media_kinds import IMAGE_EXTENSIONS, id_from_hr_stem


@dataclass(frozen=True)
class ThumbnailPolicy:
    """Rules for grid thumbnails (never serve full hrimages as a thumb)."""

    max_edge_px: int = 320
    jpeg_quality: int = 75
    derived_dir: str = "preview/derived"

    def derived_relpath(self, item_id: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in item_id)
        return f"{self.derived_dir}/{safe}.jpg"


class ThumbnailCatalog:
    """Find existing Arles / export stills suitable as grid thumbnails."""

    def __init__(self, policy: Optional[ThumbnailPolicy] = None) -> None:
        self._policy = policy or ThumbnailPolicy()

    @property
    def policy(self) -> ThumbnailPolicy:
        return self._policy

    def resolve(self, root: Path, item_id: str) -> Optional[str]:
        """Return relpath of an existing thumb, or None (caller may synthesize)."""
        root = Path(root)
        key = item_id.casefold()
        derived = root / self._policy.derived_relpath(item_id)
        if derived.is_file() and derived.stat().st_size > 0:
            return derived.relative_to(root).as_posix()

        searches = (
            (root / "thumbnails", _thumb_stem_id),
            (root / "preview", _preview_stem_id),
        )
        for folder, stem_id in searches:
            if not folder.is_dir():
                continue
            for path in folder.iterdir():
                if not path.is_file():
                    continue
                if path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                # Skip our derived folder content handled above; ignore nested.
                if stem_id(path.stem).casefold() != key:
                    continue
                return path.relative_to(root).as_posix()
        return None


def _thumb_stem_id(stem: str) -> str:
    if len(stem) > 3 and stem[:3].casefold() == "tn_":
        return stem[3:]
    return stem


def _preview_stem_id(stem: str) -> str:
    # preview/ clips may be video; stem match for stills only (caller filters ext).
    return id_from_hr_stem(stem)


class _ArtifactFiles(Protocol):
    def ensure_artifact_file(self, job_id: str, relpath: str) -> Path:
        ...

    def put_album_file(
        self,
        job_id: str,
        relpath: str,
        path: Path,
        mtime: Optional[float] = None,
    ) -> None:
        ...

    def ensure_local_root(self, job_id: str) -> Path:
        ...


class ThumbnailRenderer:
    """Ensure a small JPEG exists for grid preview (catalog hit or synthesize)."""

    def __init__(
        self,
        store: _ArtifactFiles,
        *,
        catalog: Optional[ThumbnailCatalog] = None,
        policy: Optional[ThumbnailPolicy] = None,
    ) -> None:
        self._store = store
        self._catalog = catalog or ThumbnailCatalog(policy)
        self._policy = policy or self._catalog.policy

    def ensure_thumb(
        self,
        job_id: str,
        *,
        item_id: str,
        original_relpath: str,
        thumb_relpath: Optional[str] = None,
    ) -> Path:
        root = self._store.ensure_local_root(job_id)
        preferred = thumb_relpath or self._catalog.resolve(root, item_id)
        if preferred is not None:
            path = self._store.ensure_artifact_file(job_id, preferred)
            if path.is_file() and path.stat().st_size > 0:
                return path

        derived_rel = self._policy.derived_relpath(item_id)
        derived_local = root / derived_rel
        if derived_local.is_file() and derived_local.stat().st_size > 0:
            return derived_local

        if Path(original_relpath).suffix.lower() not in IMAGE_EXTENSIONS:
            raise FileNotFoundError(original_relpath)

        original = self._store.ensure_artifact_file(job_id, original_relpath)
        if not original.is_file() or original.stat().st_size <= 0:
            raise FileNotFoundError(original_relpath)

        derived_local.parent.mkdir(parents=True, exist_ok=True)
        try:
            _render_jpeg_thumb(
                original,
                derived_local,
                max_edge=self._policy.max_edge_px,
                quality=self._policy.jpeg_quality,
            )
        except OSError as exc:
            raise FileNotFoundError(original_relpath) from exc
        try:
            self._store.put_album_file(job_id, derived_rel, derived_local)
        except Exception:
            # Local derived file is enough to serve; durable put is best-effort.
            pass
        return derived_local


def _render_jpeg_thumb(
    source: Path,
    dest: Path,
    *,
    max_edge: int,
    quality: int,
) -> None:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(source) as image:
            image = image.convert("RGB")
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            image.save(dest, format="JPEG", quality=quality, optimize=True)
    except UnidentifiedImageError as exc:
        raise OSError(str(exc)) from exc
