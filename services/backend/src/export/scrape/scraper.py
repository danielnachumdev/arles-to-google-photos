"""Download an Arles gallery into a local album tree the preview parser accepts."""
from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from ...progress import ProgressSink, emit_ops, emit_progress, raise_if_cancelled
from ..media_kinds import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, is_video_filename
from ..video_preview import ensure_local_video_previews
from .client import FetchError, FetchedResource, HttpClient, UrllibHttpClient
from .detect import (
    ArlesPageInfo,
    ArlesPageKind,
    GalleryItemRef,
    detect_arles_page,
    resolve_child_gallery_urls,
    video_embed_urls,
)
from .eta import ItemEtaTracker, saved_hr_message
from .models import ScrapeRequest, ScrapeResult

_IMAGE_EXT = set(IMAGE_EXTENSIONS)
_MEDIA_EXT = _IMAGE_EXT | set(VIDEO_EXTENSIONS)
_SKIP_IMAGE_DIRS = ("/icons/", "/thumbnails/", "\\icons\\", "\\thumbnails\\")
_SKIP_POSTER_DIRS = ("/icons/", "\\icons\\")


class NotArlesGalleryError(ValueError):
    """Start URL is not an Arles-style gallery index."""

    error_code = "not_arles"

    def __init__(self, message: str = "", *, url: str = "") -> None:
        self.url = url
        super().__init__(message or f"Not a supported Arles album: {url}".rstrip(": "))


class ScrapeFetchError(RuntimeError):
    """Required gallery resource could not be downloaded."""

    error_code = "fetch_failed"

    def __init__(
        self,
        message: str = "",
        *,
        url: str = "",
        status_code: Optional[int] = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        if message:
            text = message
        elif status_code is not None:
            text = f"Failed to download gallery: {url} (HTTP {status_code})"
        else:
            text = f"Failed to download gallery: {url}".rstrip(": ")
        super().__init__(text)


class ScrapeEmptyError(ValueError):
    """Scrape produced no album photos and no child galleries."""

    error_code = "scrape_empty"

    def __init__(self, message: str = "", *, url: str = "") -> None:
        self.url = url
        super().__init__(message or f"No album photos found: {url}".rstrip(": "))


class ArlesGalleryScraper:
    """Fetch an Arles HTML gallery and materialize ``index.html`` + ``imagepages/`` + ``hrimages/``."""

    def __init__(
        self,
        client: HttpClient | None = None,
        *,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._client = client or UrllibHttpClient()
        self._monotonic = monotonic or time.monotonic

    def scrape(
        self,
        request: ScrapeRequest,
        output_dir: Path,
        sink: ProgressSink | None = None,
    ) -> ScrapeResult:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        headers = dict(request.headers)
        start_url = request.url

        raise_if_cancelled(sink)
        _emit(
            sink,
            "scrape",
            f"Fetching gallery index: {_ui_host_label(start_url)}",
        )
        index_resource = self._require_get(start_url, headers, what="gallery index")
        _emit_ops(
            sink,
            f"GET {_safe_url(index_resource.url or start_url)} → "
            f"{index_resource.status_code}, {_format_bytes(len(index_resource.content))}",
        )
        index_url = index_resource.url or start_url
        has_arl = self._gallery_arl_exists(index_url, headers)
        info = detect_arles_page(
            index_resource.content,
            page_url=index_url,
            has_gallery_arl=has_arl,
        )
        if info.kind is ArlesPageKind.UNKNOWN:
            fps = ", ".join(info.fingerprints) if info.fingerprints else "none"
            raise NotArlesGalleryError(
                f"Not a supported Arles leaf/hub page: {start_url}. "
                f"detect kind=unknown, gallery items=0, fingerprints=[{fps}]. "
                f"Expected an Arles photo grid (imagepages/…), a parent with child "
                f"albums, or a hub listing ≥2 album indexes.",
                url=start_url,
            )

        child_urls = resolve_child_gallery_urls(index_url, info.child_gallery_hrefs)
        if info.kind in {ArlesPageKind.PARENT, ArlesPageKind.HUB}:
            if not child_urls:
                raise NotArlesGalleryError(
                    f"Not a supported Arles {info.kind.value} page: {start_url}. "
                    f"Page is classified as {info.kind.value} but no child album "
                    f"index URLs were found under this directory.",
                    url=start_url,
                )
            (output_dir / "index.html").write_bytes(index_resource.content)
            _emit_index_children(sink, info.kind, child_urls)
            return ScrapeResult(
                album_root=output_dir,
                child_gallery_urls=child_urls,
                gallery_title=info.gallery_title,
            )

        items, _extra_ids, index_bytes = self._collect_leaf_items(
            index_url,
            info,
            index_resource.content,
            headers,
            sink=sink,
        )
        if not items:
            raise ScrapeEmptyError(
                f"No album photos found at {start_url}. "
                f"Page looked like a leaf (kind={info.kind.value}) but the photo grid "
                f"was empty after merging index pages.",
                url=start_url,
            )
        (output_dir / "index.html").write_bytes(index_bytes)

        pages_dir = output_dir / "imagepages"
        hr_dir = output_dir / "hrimages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        hr_dir.mkdir(parents=True, exist_ok=True)

        total = len(items)
        tracker = ItemEtaTracker()
        _emit(
            sink,
            "scrape",
            f"Downloading album ({total} photos)",
            current=0,
            total=total,
        )
        kept = 0
        for index, item in enumerate(items, start=1):
            raise_if_cancelled(sink)
            tracker.start_item(self._monotonic())
            page_url = urljoin(index_url, item.image_page_href)
            if _is_direct_media_href(item.image_page_href):
                page_html = b"<html><body></body></html>"
                (pages_dir / f"{item.item_id}.html").write_bytes(page_html)
                page_url = index_url
            else:
                _emit_ops(
                    sink,
                    f"Fetching image page {item.item_id}: {_safe_url(page_url)}",
                    current=index,
                    total=total,
                )
                page = self._try_get(page_url, headers)
                if page is None:
                    _emit_ops(
                        sink,
                        f"Skipping missing image page {item.item_id}: "
                        f"{_safe_url(page_url)}",
                        current=index,
                        total=total,
                    )
                    continue
                _emit_ops(
                    sink,
                    f"GET {_safe_url(page.url or page_url)} → "
                    f"{page.status_code}, {_format_bytes(len(page.content))}",
                )
                page_html = page.content
                (pages_dir / f"{item.item_id}.html").write_bytes(page_html)
            _emit_ops(
                sink,
                f"Downloading hr image {item.item_id}",
                current=index,
                total=total,
            )
            try:
                image_bytes, source_name = self._download_hr_image(
                    index_url=index_url,
                    page_url=page_url,
                    item=item,
                    page_html=page_html,
                    headers=headers,
                )
            except ScrapeFetchError:
                _emit_ops(
                    sink,
                    f"Skipping missing image {item.item_id}",
                    current=index,
                    total=total,
                )
                continue
            kept += 1
            hr_name = hr_output_filename(item.item_id, source_name)
            (hr_dir / hr_name).write_bytes(image_bytes)
            _emit_ops(
                sink,
                f"GET {hr_name} → 200, {_format_bytes(len(image_bytes))}",
            )
            if is_video_filename(hr_name):
                self._download_video_poster(
                    index_url=index_url,
                    page_url=page_url,
                    item=item,
                    page_html=page_html,
                    headers=headers,
                    output_dir=output_dir,
                    sink=sink,
                    current=index,
                    total=total,
                )
            snapshot = tracker.finish_item(
                now=self._monotonic(),
                item_bytes=len(image_bytes),
                completed=index,
                total=total,
                filename=hr_name,
            )
            _emit(
                sink,
                "scrape",
                saved_hr_message(hr_name, snapshot),
                current=index,
                total=total,
                extra=snapshot.extra(),
            )

        if kept == 0:
            raise ScrapeEmptyError(
                f"No album photos could be downloaded from {start_url}. "
                f"The index listed {total} gallery item(s), but every high-res "
                f"image/page fetch failed or was missing (404/empty).",
                url=start_url,
            )

        ensure_local_video_previews(output_dir)
        return ScrapeResult(
            album_root=output_dir,
            child_gallery_urls=child_urls,
            gallery_title=info.gallery_title,
        )

    def _gallery_arl_exists(self, index_url: str, headers: Mapping[str, str]) -> bool:
        arl_url = urljoin(index_url, "Gallery.arl")
        try:
            resource = self._client.get(arl_url, headers)
        except FetchError:
            return False
        return resource.status_code == 200 and bool(resource.content)

    def _require_get(
        self,
        url: str,
        headers: Mapping[str, str],
        *,
        what: str,
    ) -> FetchedResource:
        try:
            resource = self._client.get(url, headers)
        except FetchError as exc:
            reason = str(exc).strip()
            suffix = f" — {reason}" if reason else ""
            raise ScrapeFetchError(
                f"Failed to fetch {what}: {url}{suffix}",
                url=url,
            ) from exc
        if resource.status_code != 200:
            raise ScrapeFetchError(
                f"Failed to fetch {what}: {url} (HTTP {resource.status_code})",
                url=url,
                status_code=resource.status_code,
            )
        return resource

    def _try_get(
        self,
        url: str,
        headers: Mapping[str, str],
    ) -> Optional[FetchedResource]:
        try:
            resource = self._client.get(url, headers)
        except FetchError:
            return None
        if resource.status_code != 200 or not resource.content:
            return None
        return resource

    def _collect_leaf_items(
        self,
        index_url: str,
        info: ArlesPageInfo,
        start_content: bytes,
        headers: Mapping[str, str],
        sink: ProgressSink | None = None,
    ) -> Tuple[List[GalleryItemRef], Tuple[str, ...], bytes]:
        """BFS sibling index pages; merge photos in index.html → index2 → … order."""
        page_entries: Dict[str, Tuple[int, str, bytes, Tuple[GalleryItemRef, ...]]] = {}
        start_key = _normalize_url(index_url)
        page_entries[start_key] = (
            _index_page_ordinal(index_url),
            index_url,
            start_content,
            tuple(info.items),
        )
        visited = {start_key}
        queue: List[str] = [
            urljoin(index_url, href) for href in info.paginated_index_hrefs
        ]
        while queue and len(visited) < 50:
            page_url = queue.pop(0)
            key = _normalize_url(page_url)
            if key in visited:
                continue
            visited.add(key)
            raise_if_cancelled(sink)
            _emit_ops(sink, f"Fetching index page: {_safe_url(page_url)}")
            resource = self._try_get(page_url, headers)
            if resource is None:
                continue
            resolved = resource.url or page_url
            page_info = detect_arles_page(
                resource.content,
                page_url=resolved,
            )
            page_entries[key] = (
                _index_page_ordinal(resolved),
                resolved,
                resource.content,
                tuple(page_info.items),
            )
            for more_href in page_info.paginated_index_hrefs:
                queue.append(urljoin(resolved, more_href))

        ordered_pages = sorted(
            page_entries.values(),
            key=lambda entry: (entry[0], entry[1]),
        )
        items_by_id: Dict[str, GalleryItemRef] = {}
        ordered_ids: List[str] = []
        for _ordinal, _url, _content, page_items in ordered_pages:
            for item in page_items:
                if item.item_id in items_by_id:
                    continue
                items_by_id[item.item_id] = item
                ordered_ids.append(item.item_id)

        canonical_content = ordered_pages[0][2] if ordered_pages else start_content
        canonical_ids = {item.item_id for item in ordered_pages[0][3]} if ordered_pages else set()
        extra_ids = tuple(
            item_id for item_id in ordered_ids if item_id not in canonical_ids
        )
        index_bytes = canonical_content
        if extra_ids:
            index_bytes = _append_gallery_links(index_bytes, extra_ids)
        ordered = [items_by_id[item_id] for item_id in ordered_ids]
        return ordered, extra_ids, index_bytes

    def _download_hr_image(
        self,
        *,
        index_url: str,
        page_url: str,
        item: GalleryItemRef,
        page_html: bytes,
        headers: Mapping[str, str],
    ) -> Tuple[bytes, str]:
        candidates = image_candidate_urls(
            index_url=index_url,
            page_url=page_url,
            item=item,
            page_html=page_html,
        )
        for url in candidates:
            resource = self._try_get(url, headers)
            if resource is None:
                continue
            return resource.content, _filename_from_url(url)
        raise ScrapeFetchError(
            f"No full-size image found for {item.item_id} (tried {len(candidates)} URLs)",
            url=page_url,
        )

    def _download_video_poster(
        self,
        *,
        index_url: str,
        page_url: str,
        item: GalleryItemRef,
        page_html: bytes,
        headers: Mapping[str, str],
        output_dir: Path,
        sink: ProgressSink | None,
        current: int,
        total: int,
    ) -> None:
        candidates = poster_candidate_urls(
            index_url=index_url,
            page_url=page_url,
            item=item,
            page_html=page_html,
        )
        for url in candidates:
            resource = self._try_get(url, headers)
            if resource is None:
                continue
            name = _filename_from_url(url)
            ext = Path(name).suffix or ".jpg"
            if ext.lower() not in _IMAGE_EXT:
                continue
            thumb_dir = output_dir / "thumbnails"
            thumb_dir.mkdir(parents=True, exist_ok=True)
            dest = thumb_dir / f"TN_{item.item_id}{ext}"
            dest.write_bytes(resource.content)
            _emit_ops(
                sink,
                f"GET {dest.name} → 200, {_format_bytes(len(resource.content))}",
                current=current,
                total=total,
            )
            return


def hr_output_filename(item_id: str, source_name: str) -> str:
    """Map a downloaded image onto ``hrimages/`` trailing-``hr`` naming."""
    path_name = Path(source_name)
    ext = path_name.suffix or ".JPG"
    stem = path_name.stem
    if len(stem) > 2 and stem.lower().endswith("hr") and stem[:-2] == item_id:
        return f"{stem}{ext}"
    return f"{item_id}hr{ext}"


def image_candidate_urls(
    *,
    index_url: str,
    page_url: str,
    item: GalleryItemRef,
    page_html: bytes,
) -> Tuple[str, ...]:
    """HR-first candidate URLs for the full image belonging to ``item``."""
    direct: List[str] = []
    if _is_direct_media_href(item.image_page_href):
        direct.append(urljoin(index_url, item.image_page_href))
    page_urls = _image_urls_from_page(page_html, page_url)
    video_urls = [url for url in page_urls if _is_video_url(url)]
    if video_urls or any(_is_video_url(url) for url in direct):
        ext = _preferred_extension(item, list(video_urls) + direct)
        constructed = list(_constructed_image_urls(index_url, item.item_id, ext))
        nested = _media_variant_candidate_urls(index_url, item, ext)
        ranked = _rank_image_urls(
            nested + list(video_urls) + constructed + direct
        )
        return tuple(url for url in ranked if _is_video_url(url))
    ext = _preferred_extension(item, page_urls + direct)
    constructed = _constructed_image_urls(index_url, item.item_id, ext)
    ranked = _rank_image_urls(direct + list(page_urls) + list(constructed))
    return tuple(ranked)


def _is_direct_media_href(href: str) -> bool:
    """True for a relative media file link at any depth (skips UI folders)."""
    path = unquote(href.split("#")[0].split("?")[0].replace("\\", "/")).strip("/")
    parts = [part for part in path.split("/") if part]
    if not parts:
        return False
    if any(
        part.lower() in {"icons", "thumbnails", "thumb", "thumbs", "res", "resources"}
        for part in parts[:-1]
    ):
        return False
    suffix = Path(parts[-1]).suffix.lower()
    return suffix in _MEDIA_EXT


def _media_variant_candidate_urls(
    index_url: str,
    item: GalleryItemRef,
    ext: str,
) -> List[str]:
    """Try full-size filename variants near the linked media path (path-agnostic)."""
    if not ext:
        ext = Path(item.image_page_href).suffix or ".wmv"
    if not ext.startswith("."):
        ext = f".{ext}"
    names = (
        f"{item.item_id}_Big{ext}",
        f"{item.item_id}_big{ext}",
        f"{item.item_id}{ext}",
    )
    href = item.image_page_href.replace("\\", "/")
    file_url = urljoin(index_url, href)
    gallery_base = urljoin(index_url, "./")
    urls: List[str] = []
    current = urljoin(file_url, ".")
    for _ in range(8):
        for name in names:
            urls.append(urljoin(current, name))
        if current.rstrip("/") == gallery_base.rstrip("/"):
            break
        parent = urljoin(current, "../")
        if parent == current:
            break
        current = parent
    return urls


def poster_candidate_urls(
    *,
    index_url: str,
    page_url: str,
    item: GalleryItemRef,
    page_html: bytes,
) -> Tuple[str, ...]:
    """Still-image URLs to use as a video poster (never the embed video itself)."""
    gallery_base = urljoin(index_url, "./")
    ids = _poster_item_ids(item.item_id)
    constructed: List[str] = []
    for item_id in ids:
        for ext in (".jpg", ".JPG", ".jpeg", ".JPEG", ".png", ".PNG"):
            constructed.append(urljoin(gallery_base, f"images/{item_id}{ext}"))
            constructed.append(urljoin(gallery_base, f"images/{item_id}hr{ext}"))
    thumbs: List[str] = []
    if item.thumbnail_src:
        thumbs.append(urljoin(index_url, item.thumbnail_src))
    for item_id in ids:
        for ext in (".jpg", ".JPG", ".jpeg", ".JPEG"):
            thumbs.append(urljoin(gallery_base, f"thumbnails/TN_{item_id}{ext}"))
    page_stills = _still_urls_from_page(page_html, page_url)
    return tuple(_unique_urls(constructed + thumbs + page_stills))


def _poster_item_ids(item_id: str) -> List[str]:
    ids = [item_id]
    if item_id.endswith("]") and "[" in item_id:
        bare = item_id[: item_id.rfind("[")]
        if bare and bare not in ids:
            ids.append(bare)
    return ids


def _still_urls_from_page(page_html: bytes, page_url: str) -> List[str]:
    soup = BeautifulSoup(page_html, features="html.parser")
    found: List[str] = []
    seen = set()
    for img in soup.find_all("img", src=True):
        src = str(img["src"]).replace("\\", "/")
        abs_url = urljoin(page_url, src)
        if abs_url in seen or _is_video_url(abs_url):
            continue
        path = urlparse(abs_url).path.replace("\\", "/")
        lowered = path.lower()
        if any(skip in lowered for skip in _SKIP_POSTER_DIRS):
            continue
        if Path(unquote(path)).suffix.lower() not in _IMAGE_EXT:
            continue
        seen.add(abs_url)
        found.append(abs_url)
    return found


def _unique_urls(urls: Iterable[str]) -> List[str]:
    unique: List[str] = []
    seen = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique


def _image_urls_from_page(page_html: bytes, page_url: str) -> List[str]:
    soup = BeautifulSoup(page_html, features="html.parser")
    found: List[str] = []
    seen = set()
    for img in soup.find_all("img", src=True):
        src = str(img["src"]).replace("\\", "/")
        abs_url = urljoin(page_url, src)
        if _is_full_image_url(abs_url) and abs_url not in seen:
            seen.add(abs_url)
            found.append(abs_url)
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).replace("\\", "/")
        abs_url = urljoin(page_url, href)
        if _is_full_image_url(abs_url) and abs_url not in seen:
            seen.add(abs_url)
            found.append(abs_url)
    for abs_url in video_embed_urls(page_html, page_url=page_url):
        if _is_full_image_url(abs_url) and abs_url not in seen:
            seen.add(abs_url)
            found.append(abs_url)
    return found


def _is_full_image_url(url: str) -> bool:
    path = urlparse(url).path.replace("\\", "/")
    lowered = path.lower()
    if any(skip in lowered for skip in _SKIP_IMAGE_DIRS):
        return False
    suffix = Path(path).suffix.lower()
    return suffix in _MEDIA_EXT


def _is_video_url(url: str) -> bool:
    suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    return suffix in VIDEO_EXTENSIONS


def _preferred_extension(item: GalleryItemRef, page_urls: Sequence[str]) -> str:
    for url in page_urls:
        suffix = Path(unquote(urlparse(url).path)).suffix
        if suffix and suffix.lower() in VIDEO_EXTENSIONS:
            return suffix
    for url in page_urls:
        suffix = Path(unquote(urlparse(url).path)).suffix
        if suffix:
            return suffix
    if item.thumbnail_src:
        suffix = Path(unquote(item.thumbnail_src.split("?")[0])).suffix
        if suffix:
            return suffix
    return ".JPG"


def _constructed_image_urls(index_url: str, item_id: str, ext: str) -> List[str]:
    gallery_base = urljoin(index_url, "./")
    variants = (
        f"hrimages/{item_id}hr{ext}",
        f"hrimages/{item_id}{ext}",
        f"images/{item_id}hr{ext}",
        f"images/{item_id}{ext}",
        f"originals/{item_id}{ext}",
        f"originals/{item_id}hr{ext}",
        f"{item_id}hr{ext}",
        f"{item_id}{ext}",
    )
    return [urljoin(gallery_base, rel) for rel in variants]


def _rank_image_urls(urls: Iterable[str]) -> List[str]:
    unique: List[str] = []
    seen = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)

    def score(url: str) -> Tuple[int, int, int, int]:
        path = urlparse(url).path.replace("\\", "/").lower()
        stem = Path(unquote(path)).stem
        in_hr = "/hrimages/" in path
        trailing_hr = len(stem) > 2 and stem.endswith("hr")
        in_originals = "/original" in path
        video_rank = 0 if _is_video_url(url) else 1
        hr_rank = 0 if (in_hr and trailing_hr) else 1 if in_hr else 2
        orig_rank = 0 if in_originals else 1
        trail_rank = 0 if trailing_hr else 1
        return (video_rank, hr_rank, trail_rank, orig_rank)

    unique.sort(key=score)
    return unique


def _filename_from_url(url: str) -> str:
    path = unquote(urlparse(url).path)
    name = path.rstrip("/").rsplit("/", 1)[-1]
    return name or "image.JPG"


def _append_gallery_links(index_bytes: bytes, extra_ids: Sequence[str]) -> bytes:
    snippet = "".join(
        f'<a href="imagepages/{item_id}.html"></a>\n' for item_id in extra_ids
    ).encode("ascii")
    lower = index_bytes.lower()
    marker = b"</body>"
    idx = lower.rfind(marker)
    if idx == -1:
        return index_bytes + b"\n" + snippet
    return index_bytes[:idx] + snippet + index_bytes[idx:]


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    return parsed._replace(fragment="", params="").geturl().rstrip("/") or path


def _index_page_ordinal(url: str) -> int:
    """Sort key for Arles sibling indexes: index.html/index1.html → 1, index2 → 2, …"""
    path = unquote(urlparse(url).path or "")
    basename = path.rstrip("/").rsplit("/", 1)[-1]
    lowered = basename.lower()
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


def scrape_arles_gallery(
    request: ScrapeRequest,
    output_dir: Path,
    *,
    client: HttpClient | None = None,
    sink: ProgressSink | None = None,
) -> ScrapeResult:
    return ArlesGalleryScraper(client=client).scrape(request, output_dir, sink=sink)


@dataclass(frozen=True)
class FileScrapeResult:
    """Jobs-layer shape: relative file tuples + one hop of child gallery URLs."""

    files: Tuple[Tuple[str, bytes, Optional[float]], ...]
    gallery_urls: Tuple[str, ...]


class JobsAlbumScraper:
    """``scrape(url, headers=, sink=)`` adapter used by ``src.jobs.scraper.load_default_scraper``."""

    def __init__(self, client: HttpClient | None = None) -> None:
        self._inner = ArlesGalleryScraper(client=client)

    def scrape(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
        sink: Any = None,
    ) -> FileScrapeResult:
        _emit_ops(sink, "Downloading album")
        tmp = Path(tempfile.mkdtemp(prefix="arles-scrape-"))
        try:
            result = self._inner.scrape(
                ScrapeRequest(url=url, headers=dict(headers or {})),
                tmp,
                sink=sink,
            )
            files = _tree_to_file_tuples(result.album_root)
            if result.child_gallery_urls and not (tmp / "hrimages").is_dir():
                files = ()
            _emit_ops(sink, "Download complete")
            return FileScrapeResult(
                files=files,
                gallery_urls=result.child_gallery_urls,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def get_scraper(client: HttpClient | None = None) -> JobsAlbumScraper:
    """Factory discovered by ``src.jobs.scraper.load_default_scraper``."""
    return JobsAlbumScraper(client=client)


def _tree_to_file_tuples(
    root: Path,
) -> Tuple[Tuple[str, bytes, Optional[float]], ...]:
    files: List[Tuple[str, bytes, Optional[float]]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relpath = path.relative_to(root).as_posix()
        files.append((relpath, path.read_bytes(), None))
    return tuple(files)


def _emit_index_children(
    sink: Any,
    kind: ArlesPageKind,
    child_urls: Sequence[str],
) -> None:
    count = len(child_urls)
    if kind is ArlesPageKind.HUB:
        _emit(sink, "scrape", f"Album index: {count} child albums")
        for child_url in child_urls:
            _emit_ops(sink, _safe_url(child_url))
        return
    _emit(sink, "scrape", f"Parent gallery with {count} child album(s)")


def _emit(
    sink: Any,
    stage: str,
    message: str,
    *,
    current: int = 0,
    total: int = 0,
    extra: Mapping[str, Any] | None = None,
) -> None:
    emit_progress(
        sink, stage, message, current=current, total=total, extra=extra
    )


def _emit_ops(
    sink: Any,
    message: str,
    *,
    stage: str = "scrape",
    current: int = 0,
    total: int = 0,
    extra: Mapping[str, Any] | None = None,
) -> None:
    emit_ops(
        sink,
        message,
        stage=stage,
        current=current,
        total=total,
        extra=extra,
    )


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f}KB"
    return f"{size / (1024 * 1024):.1f}MB"


def _safe_url(url: str) -> str:
    """Log a URL without query/fragment (tokens must never appear in ops logs)."""
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="", params="").geturl() or url


def _ui_host_label(url: str) -> str:
    """Hostname (or path) for user-facing scrape lines; query strings stay out of UI."""
    parsed = urlparse(url)
    return parsed.netloc or parsed.path or url
