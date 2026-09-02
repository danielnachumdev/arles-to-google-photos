"""Recognize Arles-style gallery HTML (leaf, subcategory parent, or album hub)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from .eta import VIDEO_EXTENSIONS
from ..media_kinds import id_from_hr_stem, looks_like_media_filename, normalize_loose_stem

_IMAGE_PAGE_HREF = re.compile(
    r"(?:^|/)imagepages/([^/]+)\.html?$",
    re.IGNORECASE,
)
_FLAT_MEDIA_HREF = re.compile(
    r"^([^/\\]+)\.(jpe?g|png|gif|tiff?|bmp|webp|mp4|mov|avi|wmv|m4v|webm|mkv)$",
    re.IGNORECASE,
)
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
_PAGINATED_INDEX = re.compile(r"^index(?:\d+)?\.html?$", re.IGNORECASE)
_INDEX_BASENAME = re.compile(r"^index\.html?$", re.IGNORECASE)
_THUMB_TN = re.compile(
    r"(?:^|/)thumbnails/TN_[^/]+$",
    re.IGNORECASE,
)
_DIGITAL_DUTCH = re.compile(r"digitaldutch\.com", re.IGNORECASE)
_BEGIN_TITLE = re.compile(r"<!--\s*BeginTitle\s*-->", re.IGNORECASE)
_WORD_SECTION = re.compile(r"(?:^|\s)WordSection1(?:\s|$)", re.I)
_PARAM_FILENAME = re.compile(r"^filename$", re.I)


class ArlesPageKind(str, Enum):
    LEAF = "leaf"
    PARENT = "parent"
    HUB = "hub"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class GalleryItemRef:
    item_id: str
    image_page_href: str
    thumbnail_src: Optional[str] = None


@dataclass(frozen=True)
class ArlesPageInfo:
    is_arles: bool
    kind: ArlesPageKind
    gallery_title: Optional[str]
    fingerprints: Tuple[str, ...]
    items: Tuple[GalleryItemRef, ...]
    child_gallery_hrefs: Tuple[str, ...]
    paginated_index_hrefs: Tuple[str, ...]
    journal_present: bool


def detect_arles_page(
    html: Union[str, bytes],
    *,
    page_url: str = "",
    has_gallery_arl: bool = False,
) -> ArlesPageInfo:
    """Inspect HTML (and optional Gallery.arl presence) for Arles fingerprints."""
    soup = BeautifulSoup(html, features="html.parser")
    raw = html if isinstance(html, str) else _decode_html_bytes(html)

    items = _gallery_items(soup)
    has_imagepages_grid = any(
        _IMAGE_PAGE_HREF.search(item.image_page_href) for item in items
    )
    has_direct_media_grid = bool(items) and not has_imagepages_grid
    fingerprints = _collect_fingerprints(
        soup,
        raw,
        has_gallery_arl=has_gallery_arl,
        has_imagepages_grid=has_imagepages_grid,
        has_direct_media_grid=has_direct_media_grid,
    )
    child_hrefs = _child_gallery_hrefs(soup, page_url)
    paginated = _paginated_index_hrefs(soup, page_url)
    if not items and not child_hrefs:
        items = _content_image_gallery_items(soup)
        if items:
            has_direct_media_grid = True
            fingerprints = _collect_fingerprints(
                soup,
                raw,
                has_gallery_arl=has_gallery_arl,
                has_imagepages_grid=has_imagepages_grid,
                has_direct_media_grid=has_direct_media_grid,
            )
    title = _gallery_title(soup, page_url=page_url)
    journal_present = _has_journal(soup)

    strong = {
        "gallerytitle",
        "begin_title",
        "digital_dutch",
        "imagepages_grid",
        "direct_media_grid",
        "gallery_arl",
        "thumbnail_tn",
        "imagetitle",
        "index_css",
        "image_css",
    }
    is_arles = any(name in strong for name in fingerprints)
    if items:
        kind = ArlesPageKind.LEAF
    elif child_hrefs and is_arles:
        kind = ArlesPageKind.PARENT
    elif is_arles:
        kind = ArlesPageKind.LEAF
    elif len(child_hrefs) >= 2:
        kind = ArlesPageKind.HUB
    else:
        kind = ArlesPageKind.UNKNOWN

    return ArlesPageInfo(
        is_arles=is_arles,
        kind=kind,
        gallery_title=title,
        fingerprints=fingerprints,
        items=tuple(items),
        child_gallery_hrefs=tuple(child_hrefs),
        paginated_index_hrefs=tuple(paginated),
        journal_present=journal_present,
    )


def _decode_html_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "windows-1255", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _collect_fingerprints(
    soup: BeautifulSoup,
    raw_html: str,
    *,
    has_gallery_arl: bool,
    has_imagepages_grid: bool,
    has_direct_media_grid: bool = False,
) -> Tuple[str, ...]:
    found: List[str] = []
    if soup.find("span", class_="gallerytitle") is not None:
        found.append("gallerytitle")
    if soup.find("span", class_="gallerydesc") is not None:
        found.append("gallerydesc")
    if soup.find("div", class_="imagetitle") is not None:
        found.append("imagetitle")
    if _BEGIN_TITLE.search(raw_html):
        found.append("begin_title")
    if _DIGITAL_DUTCH.search(raw_html):
        found.append("digital_dutch")
    if has_imagepages_grid:
        found.append("imagepages_grid")
    if has_direct_media_grid:
        found.append("direct_media_grid")
    if _has_thumbnail_tn(soup):
        found.append("thumbnail_tn")
    if _has_stylesheet(soup, "index.css"):
        found.append("index_css")
    if _has_stylesheet(soup, "image.css"):
        found.append("image_css")
    if has_gallery_arl:
        found.append("gallery_arl")
    if _has_journal(soup):
        found.append("word_journal")
    if _has_mso_table(soup):
        found.append("mso_table")
    if _has_video_embed(soup):
        found.append("embed_video")
    return tuple(found)


def _has_stylesheet(soup: BeautifulSoup, filename: str) -> bool:
    needle = filename.lower()
    for link in soup.find_all("link", href=True):
        href = str(link["href"]).replace("\\", "/").lower()
        if href.rstrip("/").endswith(needle):
            return True
    return False


def _has_thumbnail_tn(soup: BeautifulSoup) -> bool:
    for img in soup.find_all("img", src=True):
        src = str(img["src"]).replace("\\", "/")
        if _THUMB_TN.search(src):
            return True
    return False


def _has_journal(soup: BeautifulSoup) -> bool:
    section = soup.find("div", class_=_WORD_SECTION)
    return isinstance(section, Tag)


def _has_mso_table(soup: BeautifulSoup) -> bool:
    table = soup.find("table", class_=re.compile(r"(?:^|\s)MsoTableGrid(?:\s|$)", re.I))
    return isinstance(table, Tag)


def _gallery_title(soup: BeautifulSoup, *, page_url: str = "") -> Optional[str]:
    title_el = soup.find("span", class_="gallerytitle")
    if isinstance(title_el, Tag):
        text = _normalize_text(title_el.get_text())
        if text:
            return text
    title_tag = soup.find("title")
    text: Optional[str] = None
    if isinstance(title_tag, Tag):
        text = _normalize_text(title_tag.get_text()) or None
    if text and looks_like_media_filename(text):
        from_viewer = _imagetitle_text(soup)
        if from_viewer:
            return from_viewer
        folder = _album_dir_name_from_page_url(page_url)
        if folder:
            return folder
    if text:
        return text
    return None


def _imagetitle_text(soup: BeautifulSoup) -> Optional[str]:
    title_el = soup.find("div", class_="imagetitle")
    if not isinstance(title_el, Tag):
        return None
    text = _normalize_text(title_el.get_text(" ", strip=True))
    return text or None


def _album_dir_name_from_page_url(page_url: str) -> Optional[str]:
    if not page_url:
        return None
    path = urlparse(page_url).path or ""
    parts = [part for part in path.split("/") if part]
    if not parts:
        return None
    if _INDEX_BASENAME.match(parts[-1]):
        parts = parts[:-1]
    return unquote(parts[-1]) if parts else None


def _normalize_text(text: str) -> str:
    cleaned = text.replace("\xa0", " ")
    return " ".join(cleaned.split())


def _imagepage_anchors(soup: BeautifulSoup) -> List[Tag]:
    anchors: List[Tag] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor["href"]).replace("\\", "/")
        if _IMAGE_PAGE_HREF.search(href) is None:
            continue
        anchors.append(anchor)
    return anchors


def _gallery_grid_anchors(soup: BeautifulSoup) -> List[Tag]:
    """Thumbnail-grid membership: prefer ``<a><img>`` cells, else text-only td/li."""
    anchors = _imagepage_anchors(soup)
    with_img = [anchor for anchor in anchors if anchor.find("img") is not None]
    if with_img:
        return with_img
    text_only: List[Tag] = []
    for anchor in anchors:
        parent = anchor.parent
        if isinstance(parent, Tag) and parent.name in {"td", "li"}:
            text_only.append(anchor)
    return text_only


def _gallery_items(soup: BeautifulSoup) -> List[GalleryItemRef]:
    items: List[GalleryItemRef] = []
    seen = set()
    for anchor in _gallery_grid_anchors(soup):
        href = unquote(str(anchor["href"]).replace("\\", "/"))
        match = _IMAGE_PAGE_HREF.search(href)
        if match is None:
            continue
        item_id = id_from_hr_stem(unquote(match.group(1)))
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        thumb = None
        img = anchor.find("img", src=True)
        if isinstance(img, Tag):
            thumb = unquote(str(img["src"]).replace("\\", "/"))
        items.append(
            GalleryItemRef(
                item_id=item_id,
                image_page_href=href,
                thumbnail_src=thumb,
            )
        )
    if items:
        return items
    flat = _flat_gallery_items(soup)
    if flat:
        return flat
    return _linked_media_gallery_items(soup)


def _flat_gallery_items(soup: BeautifulSoup) -> List[GalleryItemRef]:
    """Legacy flat albums: ``<a href="id.jpg"><img …>`` in the album root."""
    items: List[GalleryItemRef] = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        if anchor.find("img") is None:
            continue
        href = unquote(str(anchor["href"]).replace("\\", "/"))
        if "/" in href.strip("/"):
            continue
        match = _FLAT_MEDIA_HREF.match(href.split("?")[0])
        if match is None:
            continue
        stem = match.group(1)
        lowered = stem.lower()
        if lowered.startswith("tn_"):
            continue
        if len(lowered) > 2 and lowered.endswith("tn"):
            continue
        item_id = normalize_loose_stem(stem)
        if item_id in seen:
            continue
        seen.add(item_id)
        thumb = None
        img = anchor.find("img", src=True)
        if isinstance(img, Tag):
            thumb = unquote(str(img["src"]).replace("\\", "/"))
        items.append(
            GalleryItemRef(
                item_id=item_id,
                image_page_href=href,
                thumbnail_src=thumb,
            )
        )
    return items


def _linked_media_gallery_items(soup: BeautifulSoup) -> List[GalleryItemRef]:
    """Media grid links at any relative path depth (skips UI folders)."""
    items: List[GalleryItemRef] = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        if anchor.find("img") is None:
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
        item_id = normalize_loose_stem(stem)
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        thumb = None
        img = anchor.find("img", src=True)
        if isinstance(img, Tag):
            thumb = unquote(str(img["src"]).replace("\\", "/"))
        items.append(
            GalleryItemRef(
                item_id=item_id,
                image_page_href=href,
                thumbnail_src=thumb,
            )
        )
    return items


def _looks_like_image_viewer(soup: BeautifulSoup) -> bool:
    """True for Digital Dutch image-viewer pages (``image.css`` / ``imagetitle``)."""
    if soup.find("div", class_="imagetitle") is not None:
        return True
    return _has_stylesheet(soup, "image.css")


def _strip_dot_slash(path: str) -> str:
    text = path
    while text.startswith("./"):
        text = text[2:]
    return text


def _content_image_gallery_items(soup: BeautifulSoup) -> List[GalleryItemRef]:
    """Single-image (or content-img) viewer: photo via ``<img src>``, not a media href grid."""
    if not _looks_like_image_viewer(soup):
        return []
    items: List[GalleryItemRef] = []
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
        item_id = normalize_loose_stem(stem)
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        items.append(
            GalleryItemRef(
                item_id=item_id,
                image_page_href=src,
                thumbnail_src=src,
            )
        )
    return items


def _paginated_index_hrefs(soup: BeautifulSoup, page_url: str) -> List[str]:
    hrefs: List[str] = []
    seen = set()
    page_dir = _directory_url(page_url)
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).replace("\\", "/")
        if _skip_href(href):
            continue
        basename = href.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        if not _PAGINATED_INDEX.match(basename):
            continue
        abs_url = urljoin(page_url, href) if page_url else href
        if page_url and _directory_url(abs_url) != page_dir:
            continue
        if href in seen:
            continue
        seen.add(href)
        hrefs.append(href)
    return hrefs


def _child_gallery_hrefs(soup: BeautifulSoup, page_url: str) -> List[str]:
    hrefs: List[str] = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).replace("\\", "/")
        if _skip_href(href):
            continue
        if _IMAGE_PAGE_HREF.search(href):
            continue
        if not _looks_like_child_index(href, page_url):
            continue
        key = _child_href_key(href, page_url)
        if key in seen:
            continue
        seen.add(key)
        hrefs.append(href)
    return hrefs


def _skip_href(href: str) -> bool:
    lowered = href.strip().lower()
    return lowered.startswith(("javascript:", "mailto:", "#"))


def _looks_like_child_index(href: str, page_url: str) -> bool:
    path = href.split("#")[0].split("?")[0]
    basename = path.rstrip("/").rsplit("/", 1)[-1] if path.rstrip("/") else ""
    is_index_file = bool(_INDEX_BASENAME.match(basename))
    is_dir_link = path.endswith("/") and "/" in path.strip("/")
    if not is_index_file and not is_dir_link:
        return False
    if not page_url:
        if "../" in path or path.startswith("/") or _is_absolute_http(path):
            return False
        parts = [part for part in path.strip("/").split("/") if part]
        # Day1/index.html → 2 parts; year/album/index.html → 3 (year TOC hubs).
        if is_index_file:
            return 2 <= len(parts) <= 3
        return 1 <= len(parts) <= 2
    abs_url = urljoin(page_url, href)
    page_dir = _directory_url(page_url)
    target_dir = _directory_url(abs_url)
    if not target_dir.startswith(page_dir):
        return False
    if target_dir == page_dir:
        return False
    relative = target_dir[len(page_dir) :].strip("/")
    parts = [part for part in relative.split("/") if part]
    # One segment: Day1/; two: 2012/1212_1/ (year index / archive hubs).
    return 1 <= len(parts) <= 2


def _is_absolute_http(href: str) -> bool:
    lowered = href.strip().lower()
    return lowered.startswith(("http://", "https://"))


def _child_href_key(href: str, page_url: str) -> str:
    if not page_url:
        return href.split("#")[0].split("?")[0].rstrip("/")
    abs_url = urljoin(page_url, href)
    parsed = urlparse(abs_url)
    path = parsed.path or "/"
    if path.endswith("/"):
        path = f"{path}index.html"
    return parsed._replace(path=path, params="", query="", fragment="").geturl()


def _directory_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    path = parsed.path or "/"
    if not path.endswith("/"):
        path = path.rsplit("/", 1)[0] + "/"
    return parsed._replace(path=path, params="", query="", fragment="").geturl()


def video_embed_urls(
    html: Union[str, bytes],
    *,
    page_url: str = "",
) -> Tuple[str, ...]:
    """Video FileName / embed / object / source URLs on a Digital Dutch image page."""
    soup = BeautifulSoup(html, features="html.parser")
    found: List[str] = []
    seen = set()
    for src in _player_media_srcs(soup):
        abs_url = urljoin(page_url, src) if page_url else src
        if not _is_video_src(abs_url):
            continue
        if abs_url in seen:
            continue
        seen.add(abs_url)
        found.append(abs_url)
    return tuple(found)


def _has_video_embed(soup: BeautifulSoup) -> bool:
    return any(_is_video_src(src) for src in _player_media_srcs(soup))


def _player_media_srcs(soup: BeautifulSoup) -> List[str]:
    srcs: List[str] = []
    for embed in soup.find_all("embed", src=True):
        if isinstance(embed, Tag):
            srcs.append(str(embed["src"]).replace("\\", "/"))
    for obj in soup.find_all("object"):
        if not isinstance(obj, Tag):
            continue
        data = obj.get("data")
        if data:
            srcs.append(str(data).replace("\\", "/"))
    for param in soup.find_all("param"):
        if not isinstance(param, Tag):
            continue
        name = str(param.get("name") or "")
        if not _PARAM_FILENAME.match(name):
            continue
        value = param.get("value")
        if value:
            srcs.append(str(value).replace("\\", "/"))
    for source in soup.find_all("source", src=True):
        if isinstance(source, Tag):
            srcs.append(str(source["src"]).replace("\\", "/"))
    return srcs


def _is_video_src(src: str) -> bool:
    path = unquote(urlparse(src).path or src.split("?")[0])
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def resolve_child_gallery_urls(
    page_url: str,
    hrefs: Sequence[str],
) -> Tuple[str, ...]:
    """Turn relative child hrefs into absolute gallery index URLs."""
    resolved: List[str] = []
    seen = set()
    for href in hrefs:
        abs_url = urljoin(page_url, href)
        parsed = urlparse(abs_url)
        path = parsed.path or "/"
        if path.endswith("/"):
            abs_url = parsed._replace(path=path + "index.html").geturl()
        if abs_url in seen:
            continue
        seen.add(abs_url)
        resolved.append(abs_url)
    return tuple(resolved)
