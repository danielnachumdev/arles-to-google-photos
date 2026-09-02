"""Parse an HTML album export into an AlbumPreview (no Google Photos I/O)."""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from ..progress import ProgressSink, raise_if_cancelled
from .media_kinds import (
    BROWSER_PLAYABLE_VIDEO,
    IMAGE_EXTENSIONS,
    KIND_VIDEO,
    VIDEO_EXTENSIONS,
    id_from_hr_stem,
    infer_item_kind,
    looks_like_media_filename,
    normalize_loose_stem,
)
from .preview import AlbumJournal, AlbumPreview, PreviewItem

INDEX_FILE_NAME = "index.html"
HR_FOLDER_NAME = "hrimages"
IMAGE_PAGES_FOLDER = "imagepages"


class AlbumStructureError(ValueError):
    """Album folder does not match a supported Arles / legacy leaf layout."""

    error_code = "album_structure"


STRUCTURE_FALLBACK_WARNING = (
    "Folder is not a standard Arles album layout. Media was imported by "
    "filename only; HTML gallery metadata (title/description/journal/captions) "
    "may be missing or incomplete."
)


_INDEX_PATTERN = re.compile(
    rf"{re.escape(Path(INDEX_FILE_NAME).stem)}\d*{re.escape(Path(INDEX_FILE_NAME).suffix)}$"
)
_IMAGE_PAGE_HREF = re.compile(
    r"(?:^|/)imagepages/([^/]+)\.html?$",
    re.IGNORECASE,
)
_FLAT_MEDIA_HREF = re.compile(
    r"^([^/\\]+)\.(jpe?g|png|gif|tiff?|bmp|webp|mp4|mov|avi|wmv|m4v|webm|mkv)$",
    re.IGNORECASE,
)
# Any-depth relative media link (last path segment is the file).
_ANY_MEDIA_HREF = re.compile(
    r"^(?P<path>(?:[^/\\]+/)*)(?P<stem>[^/\\]+)\."
    r"(?P<ext>jpe?g|png|gif|tiff?|bmp|webp|mp4|mov|avi|wmv|m4v|webm|mkv)$",
    re.IGNORECASE,
)
_SKIP_MEDIA_DIR_NAMES = frozenset(
    {
        "icons",
        "thumbnails",
        "thumb",
        "thumbs",
        "res",
        "resources",
    }
)
_TAKEN_ON_PREFIX = re.compile(r"^(\d{8})(?:_|$)")
_META_REFRESH_URL = re.compile(r"url\s*=\s*([^\s;]+)", re.IGNORECASE)
_GOOGLE_PHOTOS_HOSTS = frozenset(
    {
        "photos.app.goo.gl",
        "photos.google.com",
        "www.photos.google.com",
    }
)


def _index_file_ordinal(name: str) -> int:
    """Sort key for Arles sibling indexes: index.html/index1.html → 1, index2 → 2, …"""
    lowered = name.lower()
    if lowered in {"index.html", "index.htm"}:
        return 1
    if lowered.startswith("index") and lowered.endswith((".html", ".htm")):
        digits = ""
        for char in lowered[len("index") :]:
            if char.isdigit():
                digits += char
            else:
                break
        if digits:
            return int(digits)
    return 10**9


def _normalize_text(text: str) -> str:
    cleaned = text.replace("\xa0", " ")
    return " ".join(cleaned.split())


def _id_from_hr_stem(stem: str) -> str:
    return id_from_hr_stem(stem)


def _taken_on_from_item_id(item_id: str) -> Optional[date]:
    match = _TAKEN_ON_PREFIX.match(item_id)
    if match is None:
        return None
    raw = match.group(1)
    try:
        return date(int(raw[0:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _read_html(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "windows-1255", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class AlbumExportParser:
    """Read a local HTML album export and produce an immutable preview."""

    def parse(
        self,
        root: Path,
        sink: ProgressSink | None = None,
        *,
        allow_loose_media: bool = False,
    ) -> AlbumPreview:
        root = Path(root)
        index_path = root / INDEX_FILE_NAME
        hr_dir = root / HR_FOLDER_NAME
        pages_dir = root / IMAGE_PAGES_FOLDER

        title: Optional[str] = None
        description: Optional[str] = None
        journal: Optional[AlbumJournal] = None
        multi_index = False
        gallery_ids: List[str] = []
        index_soup: Optional[BeautifulSoup] = None

        if index_path.is_file():
            index_soup = BeautifulSoup(_read_html(index_path), features="html.parser")
            multi_index = self._is_multi_index(root)
            title, description = self._parse_index_optional(
                index_soup, multi_index=multi_index
            )
            if title is not None and looks_like_media_filename(title):
                viewer_title = self._imagetitle_text(index_soup)
                title = viewer_title or root.name
            journal = self._parse_journal(index_soup)
            # Folder exports keep index2.html… on disk; merge grids like scrape does.
            gallery_ids = self._gallery_ids_from_indexes(root)
        elif not allow_loose_media:
            raise AlbumStructureError(
                f"Album structure mismatch in '{root.name}': missing {INDEX_FILE_NAME}. "
                f"A leaf album needs {INDEX_FILE_NAME} that lists photos "
                f"(links to {IMAGE_PAGES_FOLDER}/… or root-level media files)."
            )

        hr_by_id = self._index_hr_files(hr_dir) if hr_dir.is_dir() else {}
        if gallery_ids:
            if not hr_by_id:
                hr_by_id = self._index_flat_hr_files(root, gallery_ids)
            missing = [item_id for item_id in gallery_ids if item_id not in hr_by_id]
            if missing:
                discovered = self._discover_all_media(root)
                for item_id in missing:
                    path = discovered.get(item_id)
                    if path is not None:
                        hr_by_id[item_id] = path
        ordered_ids = [item_id for item_id in gallery_ids if item_id in hr_by_id]
        structure_fallback = False

        # Flow: Arles grid → Google Photos redirect → other redirect →
        # loose-media fallback → generic structure error.
        arles_ready = bool(ordered_ids) and title is not None
        if not arles_ready:
            if index_soup is not None:
                _raise_if_index_redirect(root, index_soup)
            needs_loose = allow_loose_media and (
                not index_path.is_file()
                or title is None
                or not ordered_ids
            )
            if needs_loose:
                loose = self._discover_importable_media(root)
                if loose:
                    hr_by_id = loose
                    if gallery_ids:
                        ordered_ids = [
                            item_id for item_id in gallery_ids if item_id in loose
                        ]
                        if not ordered_ids:
                            ordered_ids = sorted(
                                loose.keys(),
                                key=lambda item_id: (
                                    loose[item_id].as_posix().casefold(),
                                    item_id.casefold(),
                                ),
                            )
                    else:
                        ordered_ids = sorted(
                            loose.keys(),
                            key=lambda item_id: (
                                loose[item_id].as_posix().casefold(),
                                item_id.casefold(),
                            ),
                        )
                    structure_fallback = True
                    title = title or root.name
                    description = None
                    journal = None
                    multi_index = False

        if not structure_fallback:
            if not index_path.is_file():
                raise AlbumStructureError(
                    f"Album structure mismatch in '{root.name}': missing {INDEX_FILE_NAME}. "
                    f"A leaf album needs {INDEX_FILE_NAME} that lists photos "
                    f"(links to {IMAGE_PAGES_FOLDER}/… or root-level media files)."
                )
            if not hr_by_id:
                raise AlbumStructureError(
                    _media_missing_message(
                        root,
                        gallery_ids=gallery_ids,
                        hr_dir_exists=hr_dir.is_dir(),
                        pages_dir_exists=pages_dir.is_dir(),
                    )
                )
            if gallery_ids and not ordered_ids:
                raise AlbumStructureError(
                    _gallery_media_mismatch_message(
                        root,
                        gallery_ids=gallery_ids,
                        media_ids=sorted(hr_by_id),
                    )
                )
            if title is None:
                raise AlbumStructureError(
                    f"Album structure mismatch in '{root.name}': {INDEX_FILE_NAME} has no gallery title. "
                    f"Expected a span.gallerytitle, another non-empty <span>, or a <title> tag."
                )

        assert title is not None
        total = len(ordered_ids)
        if sink is not None:
            sink.emit("parse", "Parsing album export", current=0, total=total)

        items: List[PreviewItem] = []
        for i, item_id in enumerate(ordered_ids, start=1):
            raise_if_cancelled(sink)
            item = self._parse_item(root, hr_by_id[item_id], pages_dir, item_id)
            items.append(item)
            if sink is not None:
                sink.emit("parse", item.relpath, current=i, total=total)

        return AlbumPreview(
            title=title,
            description=description,
            multi_index=multi_index,
            items=tuple(items),
            journal=journal,
            structure_fallback=structure_fallback,
        )

    def _is_multi_index(self, root: Path) -> bool:
        names = [path.name for path in root.iterdir() if path.is_file()]
        return sum(1 for name in names if _INDEX_PATTERN.match(name)) > 1

    def _index_paths(self, root: Path) -> List[Path]:
        paths = [
            path
            for path in root.iterdir()
            if path.is_file() and _INDEX_PATTERN.match(path.name)
        ]
        return sorted(
            paths, key=lambda path: (_index_file_ordinal(path.name), path.name.lower())
        )

    def _gallery_ids_from_indexes(self, root: Path) -> List[str]:
        """Gallery membership across ``index.html``, ``index2.html``, … in page order."""
        ids: List[str] = []
        seen = set()
        for index_path in self._index_paths(root):
            soup = BeautifulSoup(
                _read_html(index_path),
                features="html.parser",
            )
            for item_id in self._gallery_ids(soup):
                if item_id in seen:
                    continue
                seen.add(item_id)
                ids.append(item_id)
        return ids

    def _parse_index_optional(
        self,
        soup: BeautifulSoup,
        *,
        multi_index: bool,
    ) -> Tuple[Optional[str], Optional[str]]:
        title_el = soup.find("span", class_="gallerytitle")
        desc_el = soup.find("span", class_="gallerydesc")

        title: Optional[str] = None
        description: Optional[str] = None

        if isinstance(title_el, Tag) and title_el.get_text(strip=True):
            title = _normalize_text(title_el.get_text())
            if (
                not multi_index
                and isinstance(desc_el, Tag)
                and desc_el.get_text(strip=True)
            ):
                description = _normalize_text(desc_el.get_text())
        else:
            texts = [
                _normalize_text(span.get_text())
                for span in soup.find_all("span")
                if span.get_text(strip=True)
            ]
            if texts:
                title = texts[0]
                if not multi_index and len(texts) > 1:
                    description = texts[1]
            else:
                title_tag = soup.find("title")
                if isinstance(title_tag, Tag) and title_tag.get_text(strip=True):
                    title = _normalize_text(title_tag.get_text())

        if multi_index:
            description = None
        return title, description

    def _imagetitle_text(self, soup: BeautifulSoup) -> Optional[str]:
        title_el = soup.find("div", class_="imagetitle")
        if not isinstance(title_el, Tag):
            return None
        text = _normalize_text(title_el.get_text(" ", strip=True))
        return text or None

    def _parse_index(
        self,
        soup: BeautifulSoup,
        *,
        multi_index: bool,
        album_name: str = "",
    ) -> Tuple[str, Optional[str]]:
        title, description = self._parse_index_optional(soup, multi_index=multi_index)
        if title is None:
            where = f"'{album_name}'" if album_name else "album"
            raise AlbumStructureError(
                f"Album structure mismatch in {where}: {INDEX_FILE_NAME} has no gallery title. "
                f"Expected a span.gallerytitle, another non-empty <span>, or a <title> tag."
            )
        return title, description

    def _discover_all_media(self, root: Path) -> Dict[str, Path]:
        """Collect image/video files under the album (root + nested folders).

        Skips UI folders (``icons/``, ``thumbnails/``), nested child albums that
        have their own ``index.html``, and thumbnail ``tn_*`` names.
        """
        by_id: Dict[str, Path] = {}
        root = Path(root)
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            try:
                rel = current.relative_to(root)
            except ValueError:
                continue
            if any(part.lower() in _SKIP_MEDIA_DIR_NAMES for part in rel.parts):
                dirnames[:] = []
                continue
            dirnames[:] = [
                name
                for name in dirnames
                if name.lower() not in _SKIP_MEDIA_DIR_NAMES
                and not (current / name / INDEX_FILE_NAME).is_file()
            ]
            for name in filenames:
                path = current / name
                if path.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                    continue
                stem = path.stem
                lowered = stem.lower()
                if lowered.startswith("tn_") or (
                    len(lowered) > 2 and lowered.endswith("tn")
                ):
                    continue
                item_id = _normalize_loose_stem(stem)
                if not item_id:
                    continue
                existing = by_id.get(item_id)
                if existing is None or _loose_file_rank(
                    path, root
                ) < _loose_file_rank(existing, root):
                    by_id[item_id] = path
        return by_id

    def _discover_importable_media(self, root: Path) -> Dict[str, Path]:
        """Loose-media discovery that skips Flash stubs with only decorative UI assets."""
        by_id = self._discover_all_media(root)
        if not by_id:
            return {}
        if _has_flash_stub(root) and not _has_non_decorative_media(by_id):
            return {}
        return {
            item_id: path
            for item_id, path in by_id.items()
            if not _is_decorative_ui_media(path)
        }

    def _parse_journal(self, soup: BeautifulSoup) -> Optional[AlbumJournal]:
        section = soup.find(
            "div", class_=re.compile(r"(?:^|\s)WordSection1(?:\s|$)", re.I)
        )
        if not isinstance(section, Tag):
            return None
        lines: List[str] = []
        for paragraph in section.find_all("p"):
            text = _normalize_text(paragraph.get_text())
            if text:
                lines.append(text)
        if not lines:
            return None
        return AlbumJournal(heading=lines[0], paragraphs=tuple(lines[1:]))

    def _gallery_ids(self, soup: BeautifulSoup) -> List[str]:
        ids: List[str] = []
        seen = set()
        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"]).replace("\\", "/")
            match = _IMAGE_PAGE_HREF.search(href)
            if match is None:
                continue
            item_id = _id_from_hr_stem(unquote(match.group(1)))
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            ids.append(item_id)
        if ids:
            return ids
        flat = self._flat_gallery_ids(soup)
        if flat:
            return flat
        linked = self._linked_media_gallery_ids(soup)
        if linked:
            return linked
        return self._content_image_gallery_ids(soup)

    def _flat_gallery_ids(self, soup: BeautifulSoup) -> List[str]:
        ids: List[str] = []
        seen = set()
        for anchor in soup.find_all("a", href=True):
            if not isinstance(anchor, Tag) or anchor.find("img") is None:
                continue
            href = unquote(str(anchor["href"]).replace("\\", "/"))
            if "/" in href.strip("/"):
                continue
            match = _FLAT_MEDIA_HREF.match(href.split("?")[0])
            if match is None:
                continue
            stem = match.group(1)
            lowered = stem.lower()
            if lowered.startswith("tn_") or (
                len(lowered) > 2 and lowered.endswith("tn")
            ):
                continue
            item_id = _normalize_loose_stem(stem)
            if item_id in seen:
                continue
            seen.add(item_id)
            ids.append(item_id)
        return ids

    def _linked_media_gallery_ids(self, soup: BeautifulSoup) -> List[str]:
        """Gallery order from media links at any relative path depth."""
        ids: List[str] = []
        seen = set()
        for anchor in soup.find_all("a", href=True):
            if not isinstance(anchor, Tag) or anchor.find("img") is None:
                continue
            href = unquote(str(anchor["href"]).replace("\\", "/")).split("?")[0]
            match = _ANY_MEDIA_HREF.match(href)
            if match is None:
                continue
            path_prefix = match.group("path") or ""
            parts = [part for part in path_prefix.split("/") if part]
            if any(part.lower() in _SKIP_MEDIA_DIR_NAMES for part in parts):
                continue
            stem = match.group("stem")
            lowered = stem.lower()
            if lowered.startswith("tn_") or (
                len(lowered) > 2 and lowered.endswith("tn")
            ):
                continue
            item_id = _normalize_loose_stem(stem)
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            ids.append(item_id)
        return ids

    def _content_image_gallery_ids(self, soup: BeautifulSoup) -> List[str]:
        """Image-viewer indexes: photo via ``<img src>`` (href is often ``index.html``)."""
        if not _looks_like_image_viewer(soup):
            return []
        ids: List[str] = []
        seen = set()
        for img in soup.find_all("img", src=True):
            if not isinstance(img, Tag):
                continue
            src = _strip_dot_slash(
                unquote(str(img["src"]).replace("\\", "/")).split("?")[0]
            )
            match = _ANY_MEDIA_HREF.match(src)
            if match is None:
                continue
            path_prefix = match.group("path") or ""
            parts = [part for part in path_prefix.split("/") if part]
            if any(part.lower() in _SKIP_MEDIA_DIR_NAMES for part in parts):
                continue
            stem = match.group("stem")
            lowered = stem.lower()
            if lowered.startswith("tn_") or (
                len(lowered) > 2 and lowered.endswith("tn")
            ):
                continue
            item_id = _normalize_loose_stem(stem)
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            ids.append(item_id)
        return ids

    def _index_hr_files(self, hr_dir: Path) -> Dict[str, Path]:
        by_id: Dict[str, Path] = {}
        for path in hr_dir.iterdir():
            if not path.is_file():
                continue
            item_id = _id_from_hr_stem(path.stem)
            existing = by_id.get(item_id)
            if existing is None or _hr_file_rank(path) < _hr_file_rank(existing):
                by_id[item_id] = path
        return by_id

    def _index_flat_hr_files(
        self, root: Path, gallery_ids: List[str]
    ) -> Dict[str, Path]:
        """Map gallery ids to root-level ``*hr.*`` or preview files (legacy flat)."""
        by_id: Dict[str, Path] = {}
        wanted = {item_id.casefold(): item_id for item_id in gallery_ids}
        for path in root.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                continue
            stem = path.stem
            lowered = stem.lower()
            if lowered.startswith("tn_") or (
                len(lowered) > 2 and lowered.endswith("tn")
            ):
                continue
            item_id = _id_from_hr_stem(stem)
            canonical = wanted.get(item_id.casefold())
            if canonical is None:
                continue
            existing = by_id.get(canonical)
            if existing is None or _hr_file_rank(path) < _hr_file_rank(existing):
                by_id[canonical] = path
        return by_id

    def _parse_item(
        self,
        root: Path,
        image_path: Path,
        pages_dir: Path,
        item_id: str,
    ) -> PreviewItem:
        relpath = image_path.relative_to(root).as_posix()
        stat = image_path.stat()
        caption = ""
        page_path = _find_image_page(pages_dir, item_id)
        if page_path is not None:
            caption = self._parse_caption(page_path)
        if not caption:
            index_path = root / INDEX_FILE_NAME
            if index_path.is_file():
                index_soup = BeautifulSoup(
                    _read_html(index_path), features="html.parser"
                )
                if _looks_like_image_viewer(index_soup):
                    caption = self._imagetitle_text(index_soup) or ""
        kind = infer_item_kind(relpath)
        thumb_relpath = None
        play_relpath = None
        if kind == KIND_VIDEO:
            thumb_relpath = _find_thumb_relpath(root, item_id)
            play_relpath = _find_play_relpath(root, item_id, relpath)
        return PreviewItem(
            id=item_id,
            relpath=relpath,
            caption=caption,
            size_bytes=stat.st_size,
            last_modified=datetime.fromtimestamp(stat.st_mtime),
            taken_on=_taken_on_from_item_id(item_id),
            kind=kind,
            thumb_relpath=thumb_relpath,
            play_relpath=play_relpath,
        )

    def _parse_caption(self, page_path: Path) -> str:
        if not page_path.is_file():
            return ""
        soup = BeautifulSoup(_read_html(page_path), features="html.parser")
        title_el = soup.find("div", class_="imagetitle")
        if not isinstance(title_el, Tag):
            return ""
        return title_el.get_text(strip=True)


def _normalize_loose_stem(stem: str) -> str:
    return normalize_loose_stem(stem)


def _looks_like_image_viewer(soup: BeautifulSoup) -> bool:
    if soup.find("div", class_="imagetitle") is not None:
        return True
    needle = "image.css"
    for link in soup.find_all("link", href=True):
        href = str(link["href"]).replace("\\", "/").lower()
        if href.rstrip("/").endswith(needle):
            return True
    return False


def _strip_dot_slash(path: str) -> str:
    text = path
    while text.startswith("./"):
        text = text[2:]
    return text


def _find_image_page(pages_dir: Path, item_id: str) -> Optional[Path]:
    """Resolve ``imagepages/{id}.html`` or legacy ``imagepages/{id}hr.html``."""
    if not pages_dir.is_dir():
        return None
    key = item_id.casefold()
    wanted_stems = {key, f"{key}hr"}
    for path in pages_dir.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".html", ".htm"}:
            continue
        stem = path.stem
        if stem.casefold() in wanted_stems:
            return path
        if _id_from_hr_stem(stem).casefold() == key:
            return path
    return None


def _loose_file_rank(path: Path, root: Path) -> Tuple[int, int, int, str]:
    """Prefer full videos over small previews and stills (path-agnostic)."""
    stem_l = path.stem.lower()
    small_rank = 1 if "small" in stem_l else 0
    video_rank = 0 if path.suffix.lower() in VIDEO_EXTENSIONS else 1
    try:
        size_rank = -int(path.stat().st_size)
    except OSError:
        size_rank = 0
    return (small_rank, video_rank, size_rank, path.as_posix().casefold())


def _hr_file_rank(path: Path) -> Tuple[int, int]:
    """Prefer original video over still/mp4 preview copies in ``hrimages/``."""
    suffix = path.suffix.lower()
    is_video = suffix in VIDEO_EXTENSIONS
    is_browser = suffix in BROWSER_PLAYABLE_VIDEO
    trailing_hr = len(path.stem) > 2 and path.stem.lower().endswith("hr")
    if is_video and not is_browser:
        video_rank = 0
    elif is_video:
        video_rank = 1
    else:
        video_rank = 2
    hr_rank = 0 if trailing_hr else 1
    return (video_rank, hr_rank)


def _thumb_stem_id(stem: str) -> str:
    if len(stem) > 3 and stem[:3].casefold() == "tn_":
        return stem[3:]
    return stem


def _find_thumb_relpath(root: Path, item_id: str) -> Optional[str]:
    key = item_id.casefold()
    searches = (
        (root / "thumbnails", _thumb_stem_id),
        (root / "preview", lambda stem: stem),
        (root / "hrimages", _id_from_hr_stem),
    )
    for folder, stem_id in searches:
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if stem_id(path.stem).casefold() != key:
                continue
            return path.relative_to(root).as_posix()
    return None


def _find_play_relpath(root: Path, item_id: str, relpath: str) -> Optional[str]:
    if Path(relpath).suffix.lower() in BROWSER_PLAYABLE_VIDEO:
        return relpath
    key = item_id.casefold()
    preview_dir = root / "preview"
    if preview_dir.is_dir():
        for path in preview_dir.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in BROWSER_PLAYABLE_VIDEO:
                continue
            if path.stem.casefold() == key:
                return path.relative_to(root).as_posix()
    hr_dir = root / "hrimages"
    if hr_dir.is_dir():
        for path in hr_dir.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in BROWSER_PLAYABLE_VIDEO:
                continue
            if _id_from_hr_stem(path.stem).casefold() != key:
                continue
            rel = path.relative_to(root).as_posix()
            if rel != relpath:
                return rel
    return None


def _child_album_names(root: Path, *, limit: int = 8) -> List[str]:
    names: List[str] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return names
    for path in entries:
        if not path.is_dir():
            continue
        if (path / INDEX_FILE_NAME).is_file():
            names.append(path.name)
            if len(names) >= limit:
                break
    return names


def _count_root_media(root: Path) -> int:
    count = 0
    try:
        entries = list(root.iterdir())
    except OSError:
        return 0
    for path in entries:
        if not path.is_file():
            continue
        if path.suffix.lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            stem = path.stem.lower()
            if stem.startswith("tn_") or (len(stem) > 2 and stem.endswith("tn")):
                continue
            count += 1
    return count


def _count_hrimages_files(root: Path) -> int:
    hr_dir = root / HR_FOLDER_NAME
    if not hr_dir.is_dir():
        return 0
    try:
        return sum(1 for path in hr_dir.iterdir() if path.is_file())
    except OSError:
        return 0


def _has_flash_stub(root: Path) -> bool:
    try:
        return any(path.suffix.lower() == ".swf" for path in root.iterdir() if path.is_file())
    except OSError:
        return False


def _is_decorative_ui_media(path: Path) -> bool:
    """Home/nav icons next to Flash stubs are not album photos."""
    suffix = path.suffix.lower()
    name = path.name.lower()
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    if suffix == ".gif" and size < 50_000:
        return True
    if any(token in name for token in ("tsign", "home", "nav", "button", "icon")):
        if suffix in {".gif", ".png", ".jpg", ".jpeg"} and size < 100_000:
            return True
    return False


def _has_non_decorative_media(by_id: Dict[str, Path]) -> bool:
    return any(not _is_decorative_ui_media(path) for path in by_id.values())


def _meta_refresh_url(soup: BeautifulSoup) -> Optional[str]:
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


def _is_google_photos_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    if host in _GOOGLE_PHOTOS_HOSTS:
        return True
    if host.endswith(".google.com") and "/photos" in (parsed.path or "").lower():
        return True
    return False


def _raise_if_index_redirect(root: Path, soup: BeautifulSoup) -> None:
    """Fail closed on meta-refresh stubs before loose-media fallback.

    Order: Google Photos share links, then any other http-equiv refresh.
    """
    target = _meta_refresh_url(soup)
    if not target:
        return
    if _is_google_photos_url(target):
        raise AlbumStructureError(
            f"Album '{root.name}' only redirects to Google Photos ({target}). "
            f"There is no Arles HTML gallery here to import — open that Google Photos "
            f"link in a browser, or use a folder that still has the original album files."
        )
    raise AlbumStructureError(
        f"Album '{root.name}' only redirects to another page ({target}). "
        f"There is no photo album to import from this index.html."
    )


def _media_missing_message(
    root: Path,
    *,
    gallery_ids: List[str],
    hr_dir_exists: bool,
    pages_dir_exists: bool,
) -> str:
    children = _child_album_names(root)
    flat_media = _count_root_media(root)
    hr_files = _count_hrimages_files(root)
    flash = _has_flash_stub(root)
    found = (
        f"Found: {INDEX_FILE_NAME}=yes, "
        f"{HR_FOLDER_NAME}/={'yes' if hr_dir_exists else 'no'}"
        f"{f' ({hr_files} files)' if hr_dir_exists else ''}, "
        f"{IMAGE_PAGES_FOLDER}/={'yes' if pages_dir_exists else 'no'}, "
        f"gallery links in index={len(gallery_ids)}, "
        f"root media candidates={flat_media}"
    )
    if children:
        preview = ", ".join(children[:6])
        more = "" if len(children) <= 6 else ", …"
        found += f", child albums with {INDEX_FILE_NAME}={len(children)} ({preview}{more})"
    expected = (
        "Expected a leaf photo album with either:\n"
        f"  • standard Arles: {HR_FOLDER_NAME}/*hr.* matching gallery links, or\n"
        "  • legacy flat: *hr.* / preview media in the album root linked from index.html"
    )
    hint = ""
    if children and not gallery_ids:
        hint = (
            " Hint: this looks like a parent/hub folder (sub-albums), "
            "not a leaf photo gallery."
        )
    elif flash and not gallery_ids:
        hint = (
            " Hint: this folder exists as a Flash/non-photo page (e.g. .swf showcase), "
            "not a missing album and not a photo gallery to import."
        )
    elif gallery_ids and not hr_dir_exists and flat_media == 0:
        hint = (
            " Hint: index.html lists photos, but no matching media files were found "
            f"under {HR_FOLDER_NAME}/ or in the album root."
        )
    elif hr_dir_exists and hr_files == 0:
        hint = f" Hint: {HR_FOLDER_NAME}/ exists but is empty."
    return (
        f"Album structure mismatch in '{root.name}': no photo/video files to import. "
        f"{expected} {found}.{hint}"
    )


def _gallery_media_mismatch_message(
    root: Path,
    *,
    gallery_ids: List[str],
    media_ids: List[str],
) -> str:
    sample_links = ", ".join(gallery_ids[:5])
    sample_media = ", ".join(media_ids[:5]) if media_ids else "(none)"
    return (
        f"Album structure mismatch in '{root.name}': index gallery links do not match "
        f"available media files. "
        f"Gallery ids ({len(gallery_ids)}): {sample_links}"
        f"{'…' if len(gallery_ids) > 5 else ''}. "
        f"Media ids ({len(media_ids)}): {sample_media}"
        f"{'…' if len(media_ids) > 5 else ''}. "
        f"Names must align after stripping a trailing 'hr' from {HR_FOLDER_NAME}/ stems."
    )
