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
from ..work_lane import AdaptiveWorkLane, TransientError
from .models import RemoteAlbumSnapshot, RemoteItemSnapshot
from .titles import assign_title_ids

_INDEX_ORDINAL = re.compile(r"index(?:(\d+))?\.html?$", re.IGNORECASE)
_TRANSIENT_HTTP = frozenset({408, 429, 500, 502, 503, 504})


def _http_is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (TransientError, FetchError, TimeoutError, ConnectionError)):
        return True
    status = getattr(exc, "status_code", None)
    try:
        return int(status) in _TRANSIENT_HTTP
    except (TypeError, ValueError):
        return False


class _HttpStatusError(Exception):
    def __init__(self, status_code: int, url: str) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(f"HTTP {status_code} for {url}")


class RemoteAlbumDiscovery:
    """Walk hub/parent/leaf Arles pages; HEAD media sizes; GET captions only."""

    def __init__(
        self,
        client: Optional[HttpClient] = None,
        *,
        lane: Optional[AdaptiveWorkLane] = None,
        max_workers: int = 8,
    ) -> None:
        self._client = client or UrllibHttpClient()
        self._lane = lane
        self._max_workers = max_workers

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
        own_lane = self._lane is None
        lane = self._lane or AdaptiveWorkLane(
            max_workers=self._max_workers,
            is_transient=_http_is_transient,
        )
        try:
            while queue:
                raise_if_cancelled(sink)
                wave: List[str] = []
                while queue:
                    page_url = queue.pop(0)
                    key = _normalize_url(page_url)
                    if key in visited:
                        continue
                    visited.add(key)
                    wave.append(page_url)
                if not wave:
                    break
                emit_progress(
                    sink,
                    stage="discover",
                    message=f"Fetching {len(wave)} page(s)",
                    current=len(visited),
                    total=max(len(visited), 1),
                )
                fetched = lane.map(
                    [
                        (lambda url=page_url: self._get_page(url, header_map))
                        for page_url in wave
                    ]
                )
                for page_url, (resource, fetch_warning) in zip(wave, fetched):
                    raise_if_cancelled(sink)
                    if resource is None:
                        if fetch_warning:
                            warnings.append(fetch_warning)
                        continue
                    resolved = resource.url or page_url
                    info = detect_arles_page(resource.content, page_url=resolved)
                    if info.kind == ArlesPageKind.UNKNOWN:
                        warnings.append(
                            f"Not an Arles gallery page: {resolved} "
                            f"(kind=unknown, fingerprints="
                            f"{list(info.fingerprints) or 'none'})"
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
                            if _normalize_url(child) not in visited:
                                queue.append(child)
                        continue
                    items, leaf_warnings = self._leaf_items(
                        resolved,
                        info,
                        resource.content,
                        header_map,
                        sink=sink,
                        lane=lane,
                    )
                    warnings.extend(leaf_warnings)
                    title = (
                        (info.gallery_title or "").strip()
                        or _fallback_title(resolved)
                    )
                    raw_albums.append((title, resolved, tuple(items)))
        finally:
            if own_lane:
                lane.close(wait=True)

        title_ids, collision_warnings = assign_title_ids(
            [title for title, _url, _items in raw_albums]
        )
        warnings.extend(collision_warnings)
        return [
            RemoteAlbumSnapshot(
                title_id=title_ids[i],
                title=title,
                url=url,
                items=items,
            )
            for i, (title, url, items) in enumerate(raw_albums)
        ], warnings

    def _leaf_items(
        self,
        index_url: str,
        info: ArlesPageInfo,
        start_content: bytes,
        headers: Mapping[str, str],
        *,
        sink: ProgressSink | None,
        lane: AdaptiveWorkLane,
    ) -> Tuple[List[RemoteItemSnapshot], List[str]]:
        refs = self._merge_index_items(
            index_url, info, start_content, headers, sink, lane
        )
        warnings: List[str] = []
        total = len(refs)
        emit_progress(
            sink,
            stage="discover",
            message=f"Inspecting {total} item(s)",
            current=0,
            total=max(total, 1),
        )

        def inspect(item: GalleryItemRef) -> RemoteItemSnapshot:
            # Runs inside the lane worker — call HTTP client directly (no nested
            # lane.submit) so we cannot deadlock on the shared worker pool.
            page_url = urljoin(index_url, item.image_page_href)
            page_html, caption = self._fetch_caption(page_url, headers)
            media_url, size = self._head_media_size(
                index_url=index_url,
                page_url=page_url,
                item=item,
                page_html=page_html or b"",
                headers=headers,
            )
            return RemoteItemSnapshot(
                item_id=item.item_id,
                caption=(caption or "").strip(),
                byte_size=size,
                media_url=media_url,
            )

        snapshots = lane.map([lambda item=item: inspect(item) for item in refs])
        for snap in snapshots:
            if snap.byte_size is None:
                warnings.append(
                    f"size_unavailable for remote item {snap.item_id}"
                )
        return snapshots, warnings

    def _merge_index_items(
        self,
        index_url: str,
        info: ArlesPageInfo,
        start_content: bytes,
        headers: Mapping[str, str],
        sink: ProgressSink | None,
        lane: AdaptiveWorkLane,
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
            wave: List[str] = []
            while queue and len(visited) + len(wave) < 50:
                page_url = queue.pop(0)
                key = _normalize_url(page_url)
                if key in visited:
                    continue
                visited.add(key)
                wave.append(page_url)
            if not wave:
                break
            fetched = lane.map(
                [
                    (lambda url=page_url: self._try_get(url, headers))
                    for page_url in wave
                ]
            )
            for page_url, resource in zip(wave, fetched):
                if resource is None:
                    continue
                resolved = resource.url or page_url
                page_info = detect_arles_page(resource.content, page_url=resolved)
                page_entries[_normalize_url(resolved)] = (
                    _index_page_ordinal(resolved),
                    resolved,
                    tuple(page_info.items),
                )
                for more_href in page_info.paginated_index_hrefs:
                    more = urljoin(resolved, more_href)
                    if _normalize_url(more) not in visited:
                        queue.append(more)

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
            except FetchError as exc:
                raise TransientError(str(exc)) from exc
            if resource.status_code in _TRANSIENT_HTTP:
                raise _HttpStatusError(resource.status_code, url)
            if resource.status_code >= 400:
                continue
            size = _content_length(resource.headers)
            if size is not None:
                return url, size
            try:
                got = self._client.get(url, headers)
            except FetchError as exc:
                raise TransientError(str(exc)) from exc
            if got.status_code in _TRANSIENT_HTTP:
                raise _HttpStatusError(got.status_code, url)
            if got.status_code >= 400:
                continue
            size = _content_length(got.headers)
            if size is None:
                size = len(got.content) if got.content else None
            if size is not None:
                return url, size
        return None, None

    def _get_page(
        self, url: str, headers: Mapping[str, str]
    ) -> Tuple[Optional[FetchedResource], Optional[str]]:
        try:
            resource = self._client.get(url, headers)
        except FetchError as exc:
            raise TransientError(str(exc)) from exc
        if resource.status_code in _TRANSIENT_HTTP:
            raise _HttpStatusError(resource.status_code, url)
        if resource.status_code != 200:
            return None, f"Could not fetch {url} (HTTP {resource.status_code})"
        if not resource.content:
            return None, f"Could not fetch {url} (empty body)"
        return resource, None

    def _try_get(
        self, url: str, headers: Mapping[str, str]
    ) -> Optional[FetchedResource]:
        resource, _warning = self._get_page(url, headers)
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
