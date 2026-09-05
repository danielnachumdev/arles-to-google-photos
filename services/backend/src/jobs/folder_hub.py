"""Detect Arles folder hubs and fan out leaf preview children."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Protocol, Sequence, Tuple
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

ALBUM_RELPATH_KEY = "album_relpath"
INDEX_FILE_NAME = "index.html"
_IMAGEPAGES_HREF = re.compile(
    r"(?:^|/)imagepages/([^/]+)\.html?$",
    re.IGNORECASE,
)
_META_REFRESH_URL = re.compile(
    r"url\s*=\s*([^;]+)",
    re.IGNORECASE,
)


class FolderAlbumKind(str, Enum):
    LEAF = "leaf"
    HUB = "hub"


@dataclass(frozen=True)
class FolderHubPlan:
    kind: FolderAlbumKind
    child_relpaths: Tuple[str, ...] = ()


class FolderHubDetector:
    """Classify an on-disk album root as a leaf gallery or a hub of child albums."""

    def detect(self, root: Path) -> FolderHubPlan:
        root = Path(root)
        children = _child_album_relpaths(root)
        index_path = root / INDEX_FILE_NAME
        if not index_path.is_file():
            if children:
                return FolderHubPlan(FolderAlbumKind.HUB, children)
            return FolderHubPlan(FolderAlbumKind.LEAF, ())

        raw = index_path.read_bytes()
        soup = BeautifulSoup(_decode_html(raw), "html.parser")
        if _has_photo_grid(soup):
            return FolderHubPlan(FolderAlbumKind.LEAF, ())

        refresh = _meta_refresh_target(soup)
        if refresh is not None:
            child_from_refresh = _relpath_dir_from_href(refresh)
            if children:
                return FolderHubPlan(FolderAlbumKind.HUB, children)
            if child_from_refresh is not None and (root / child_from_refresh / INDEX_FILE_NAME).is_file():
                return FolderHubPlan(FolderAlbumKind.HUB, (child_from_refresh,))
            return FolderHubPlan(FolderAlbumKind.HUB, ())

        if children:
            return FolderHubPlan(FolderAlbumKind.HUB, children)
        return FolderHubPlan(FolderAlbumKind.LEAF, ())


class _StoreLike(Protocol):
    def create(
        self,
        base_dir: Path,
        *,
        folder_label: Optional[str] = None,
        job_type: str = "preview",
        parent_job_id: Optional[str] = None,
        source_job_id: Optional[str] = None,
        auto_publish: bool = False,
        import_origin: Optional[str] = None,
        owner_id: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> object:
        ...

    def get(self, job_id: str) -> object:
        ...

    def set_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None,
        *,
        job_type: Optional[str] = None,
    ) -> object:
        ...

    def has_active_descendants(self, job_id: str) -> bool:
        ...

    def list_children(self, parent_id: str) -> Sequence[object]:
        ...


class FolderHubFanOut:
    """Create shared-artifact preview children for each hub leaf and enqueue them."""

    def __init__(
        self,
        store: _StoreLike,
        *,
        jobs_root: Path,
        submit: Callable[[str, Callable[[], None]], None],
        run_child: Callable[[str], None],
        events_emit: Optional[Callable[..., None]] = None,
    ) -> None:
        self._store = store
        self._jobs_root = Path(jobs_root)
        self._submit = submit
        self._run_child = run_child
        self._emit = events_emit

    def apply(self, parent_id: str, plan: FolderHubPlan) -> Tuple[str, ...]:
        if plan.kind != FolderAlbumKind.HUB or not plan.child_relpaths:
            return ()
        parent = self._store.get(parent_id)
        auto_publish = bool(getattr(parent, "auto_publish", False))
        owner_id = getattr(parent, "owner_id", None)
        import_origin = getattr(parent, "import_origin", None) or "folder"
        child_ids: list[str] = []
        for rel in plan.child_relpaths:
            child = self._store.create(
                self._jobs_root,
                folder_label=rel,
                job_type="preview",
                parent_job_id=parent_id,
                source_job_id=parent_id,
                auto_publish=auto_publish,
                import_origin=import_origin,
                owner_id=owner_id,
                extra={ALBUM_RELPATH_KEY: rel},
            )
            child_id = str(getattr(child, "id"))
            child_ids.append(child_id)
            if self._emit is not None:
                self._emit(
                    parent_id,
                    "child",
                    child_id,
                    extra={"child_id": child_id, "type": "preview", "album_relpath": rel},
                )
            self._enqueue(child_id)
        if self._store.has_active_descendants(parent_id):
            self._store.set_status(parent_id, "waiting", job_type="preview")
            if self._emit is not None:
                self._emit(parent_id, "waiting", parent_id)
        else:
            self._store.set_status(parent_id, "done", job_type="preview")
            if self._emit is not None:
                self._emit(parent_id, "done", parent_id)
        return tuple(child_ids)

    def _enqueue(self, child_id: str) -> None:
        run_child = self._run_child

        def _fn() -> None:
            run_child(child_id)

        self._submit(child_id, _fn)


def album_relpath_of(job: object) -> Optional[str]:
    extra = getattr(job, "extra", None) or {}
    if not isinstance(extra, dict):
        return None
    raw = extra.get(ALBUM_RELPATH_KEY)
    if raw is None:
        return None
    text = str(raw).replace("\\", "/").strip().strip("/")
    if not text or text.startswith("..") or "/../" in f"/{text}/":
        return None
    return text


def artifact_relpath_for(job: object, relpath: str) -> str:
    """Map album-relative path to durable artifact path (prefix album_relpath)."""
    rel = (relpath or "").replace("\\", "/").lstrip("/")
    base = album_relpath_of(job)
    if not base:
        return rel
    if not rel:
        return base
    return f"{base}/{rel}"


def _child_album_relpaths(root: Path) -> Tuple[str, ...]:
    names: list[str] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name.casefold())
    except OSError:
        return ()
    for path in entries:
        if not path.is_dir():
            continue
        if (path / INDEX_FILE_NAME).is_file():
            names.append(path.name)
    return tuple(names)


def _has_photo_grid(soup: BeautifulSoup) -> bool:
    for anchor in soup.find_all("a"):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href") or "").replace("\\", "/")
        if _IMAGEPAGES_HREF.search(href):
            return True
    return False


def _meta_refresh_target(soup: BeautifulSoup) -> Optional[str]:
    for meta in soup.find_all("meta"):
        if not isinstance(meta, Tag):
            continue
        equiv = str(meta.get("http-equiv") or "").strip().lower()
        if equiv != "refresh":
            continue
        content = str(meta.get("content") or "")
        match = _META_REFRESH_URL.search(content)
        if match is None:
            continue
        return match.group(1).strip().strip("\"'")
    return None


def _relpath_dir_from_href(href: str) -> Optional[str]:
    raw = unquote((href or "").strip())
    if not raw or raw.startswith(("http://", "https://", "//")):
        return None
    parsed = urlparse(raw)
    path = (parsed.path or raw).replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    path = path.lstrip("/")
    if not path or path.startswith(".."):
        return None
    parts = [part for part in path.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        return None
    if not parts:
        return None
    if parts[-1].lower() in {INDEX_FILE_NAME.lower(), "index.htm"}:
        parts = parts[:-1]
    if not parts:
        return None
    return parts[0]


def _decode_html(raw: bytes) -> str:
    for encoding in ("utf-8", "windows-1255", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")
