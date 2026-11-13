"""BFS remote Arles discovery without materializing hrimages."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ...progress import ProgressSink, emit_progress, raise_if_cancelled
from ..scrape.client import FetchError, FetchedResource, HttpClient, UrllibHttpClient
from ..scrape.detect import (
    ArlesPageInfo,
    ArlesPageKind,
    GalleryItemRef,
    detect_arles_page,
    resolve_child_gallery_urls,
)
from ..scrape.scraper import image_candidate_urls
from .models import RemoteAlbumSnapshot, RemoteItemSnapshot
from .titles import assign_title_ids

_INDEX_ORDINAL = re.compile(r"index(?:(\d+))?\.html?$", re.IGNORECASE)


class RemoteAlbumDiscovery:
    """Walk hub/parent/leaf Arles pages; HEAD media sizes; GET captions only."""

    def __init__(self, client: Optional[HttpClient] = None) -> None:
        self._client = client or UrllibHttpClient()

    def discover(
        self,
        root_url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        sink: ProgressSink | None = None,
    ) -> Tuple[List[RemoteAlbumSnapshot], List[str]]:
        header_map = dict(headers or {})
        queue: List[str] = [root_url.strip()]
        visited: Set[str] = set()
        raw_albums: List[Tuple[str, str, Tuple[RemoteItemSnapshot, ...]]] = []
        warnings: List[str] = []

        while queue:
            raise_if_cancelled(sink)
            page_url = queue.pop(0)
            key = _normalize_url(page_url)
            if key in visited:
                continue
            visited.add(key)
            emit_progress(
                sink,
                stage="discover",
                message=f"Fetching {page_url}",
                current=len(visited),
                total=max(len(visited) + len(queue), 1),
            )
            resource, fetch_warning = self._fetch_page(page_url, header_map)
            if resource is None:
                if fetch_warning:
                    warnings.append(fetch_warning)
                continue
            resolved = resource.url or page_url
            info = detect_arles_page(resource.content, page_url=resolved)
            # Hubs are intentionally non-Arles (album-list pages). Match scraper:
            # only UNKNOWN is rejected.
            if info.kind == ArlesPageKind.UNKNOWN:
                warnings.append(
                    f"Not an Arles gallery page: {resolved} "
                    f"(kind=unknown, fingerprints={list(info.fingerprints) or 'none'})"
                )
                continue
            if info.kind in {ArlesPageKind.PARENT, ArlesPageKind.HUB}:
                children = resolve_child_gallery_urls(
                    resolved, info.child_gallery_hrefs
                )
                if not children:
                    warnings.append(
                        f"Hub/parent with no child albums: {resolved}"
                    )
                    continue
                for child in children:
                    child_key = _normalize_url(child)
                    if child_key not in visited:
                        queue.append(child)
                continue
            # LEAF
            items, leaf_warnings = self._leaf_items(
                resolved, info, resource.content, header_map, sink=sink
            )
            warnings.extend(leaf_warnings)
            title = (info.gallery_title or "").strip() or _fallback_title(resolved)
            raw_albums.append((title, resolved, tuple(items)))

        title_ids, collision_warnings = assign_title_ids(
            [title for title, _url, _items in raw_albums]
        )
        warnings.extend(collision_warnings)
        albums = [
            RemoteAlbumSnapshot(
                title_id=title_ids[i],
                title=title,
                url=url,
                items=items,
            )
            for i, (title, url, items) in enumerate(raw_albums)
        ]
        return albums, warnings

    def _leaf_items(
        self,
        index_url: str,
        info: ArlesPageInfo,
        start_content: bytes,
        headers: Mapping[str, str],
        *,
        sink: ProgressSink | None,
    ) -> Tuple[List[RemoteItemSnapshot], List[str]]:
        refs = self._merge_index_items(index_url, info, start_content, headers, sink)
        snapshots: List[RemoteItemSnapshot] = []
        warnings: List[str] = []
        total = len(refs)
        for i, item in enumerate(refs, start=1):
            raise_if_cancelled(sink)
            emit_progress(
                sink,
                stage="discover",
                message=f"Inspecting {item.item_id}",
                current=i,
                total=total,
            )
            page_url = urljoin(index_url, item.image_page_href)
            page_html, caption = self._fetch_caption(page_url, headers)
            media_url, size = self._head_media_size(
                index_url=index_url,
                page_url=page_url,
                item=item,
                page_html=page_html or b"",
                headers=headers,
            )
            if size is None:
                warnings.append(f"size_unavailable for remote item {item.item_id}")
            snapshots.append(
                RemoteItemSnapshot(
                    item_id=item.item_id,
                    caption=(caption or "").strip(),
                    byte_size=size,
                    media_url=media_url,
                )
            )
        return snapshots, warnings

    def _merge_index_items(
        self,
        index_url: str,
        info: ArlesPageInfo,
        start_content: bytes,
        headers: Mapping[str, str],
        sink: ProgressSink | None,
    ) -> List[GalleryItemRef]:
        page_entries: Dict[str, Tuple[int, str, Tuple[GalleryItemRef, ...]]] = {}
        start_key = _normalize_url(index_url)
        page_entries[start_key] = (
            _index_page_ordinal(index_url),
            index_url,
            tuple(info.items),
        )
        visited = {start_key}
        queue: List[str] = [
            urljoin(index_url, href) for href in info.paginated_index_hrefs
        ]
        while queue and len(visited) < 50:
            raise_if_cancelled(sink)
            page_url = queue.pop(0)
            key = _normalize_url(page_url)
            if key in visited:
                continue
            visited.add(key)
            resource = self._try_get(page_url, headers)
            if resource is None:
                continue
            resolved = resource.url or page_url
            page_info = detect_arles_page(resource.content, page_url=resolved)
            page_entries[key] = (
                _index_page_ordinal(resolved),
                resolved,
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
        for _ord, _url, page_items in ordered_pages:
            for item in page_items:
                if item.item_id in items_by_id:
                    continue
                items_by_id[item.item_id] = item
                ordered_ids.append(item.item_id)
        return [items_by_id[item_id] for item_id in ordered_ids]

    def _fetch_caption(
        self, page_url: str, headers: Mapping[str, str]
    ) -> Tuple[Optional[bytes], str]:
        resource = self._try_get(page_url, headers)
        if resource is None or resource.status_code != 200:
            return None, ""
        soup = BeautifulSoup(resource.content, features="html.parser")
        title_el = soup.find("div", class_="imagetitle")
        if title_el is None:
            return resource.content, ""
        return resource.content, title_el.get_text(" ", strip=True)

    def _head_media_size(
        self,
        *,
        index_url: str,
        page_url: str,
        item: GalleryItemRef,
        page_html: bytes,
        headers: Mapping[str, str],
    ) -> Tuple[Optional[str], Optional[int]]:
        candidates = image_candidate_urls(
            index_url=index_url,
            page_url=page_url,
            item=item,
            page_html=page_html,
        )
        for url in candidates:
            try:
                resource = self._client.head(url, headers)
            except FetchError:
                continue
            if resource.status_code >= 400:
                continue
            size = _content_length(resource.headers)
            if size is not None:
                return url, size
            # Some hosts reject HEAD; fall back to a ranged GET via full get
            # only to read headers — still avoid storing body as artifact.
            try:
                got = self._client.get(url, headers)
            except FetchError:
                continue
            if got.status_code >= 400:
                continue
            size = _content_length(got.headers)
            if size is None:
                size = len(got.content) if got.content else None
            if size is not None:
                return url, size
        return None, None

    def _fetch_page(
        self, url: str, headers: Mapping[str, str]
    ) -> Tuple[Optional[FetchedResource], Optional[str]]:
        """GET ``url``. Returns ``(resource, warning)``; warning set on failure."""
        try:
            resource = self._client.get(url, headers)
        except FetchError as exc:
            return None, f"Could not fetch {url}: {exc}"
        if resource.status_code != 200:
            return None, f"Could not fetch {url} (HTTP {resource.status_code})"
        if not resource.content:
            return None, f"Could not fetch {url} (empty body)"
        return resource, None

    def _try_get(self, url: str, headers: Mapping[str, str]):
        resource, _warning = self._fetch_page(url, headers)
        return resource


def _content_length(headers: Mapping[str, str]) -> Optional[int]:
    raw = headers.get("content-length") or headers.get("Content-Length")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    path = parsed.path or "/"
    if path.endswith("/"):
        path = path + "index.html"
    return parsed._replace(path=path, fragment="", query="").geturl().lower()


def _index_page_ordinal(url: str) -> int:
    name = Path(urlparse(url).path or "").name
    match = _INDEX_ORDINAL.search(name)
    if not match:
        return 10_000
    if match.group(1) is None or match.group(1) == "":
        return 1
    return int(match.group(1))


def _fallback_title(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    parts = [p for p in path.split("/") if p and not p.lower().startswith("index")]
    return parts[-1] if parts else url
