"""Album scraper Protocol used by scrape jobs.

The HTML implementation lives in ``src.export.scrape`` (owned separately).
This module is the jobs-layer contract plus a loader that adapts a real
scraper when present.
"""
from __future__ import annotations

import importlib
import inspect
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Mapping, Optional, Protocol, Sequence, Tuple
from urllib.parse import urlparse

_STATE_NAMES = frozenset(
    {"job.json", "events.json", "job.json.tmp", "events.json.tmp"}
)

FileTuple = Tuple[str, bytes, Optional[float]]


@dataclass(frozen=True)
class ScrapeResult:
    """Downloaded album tree plus optional extra gallery URLs (one hop)."""

    files: Sequence[FileTuple] = field(default_factory=tuple)
    gallery_urls: Sequence[str] = field(default_factory=tuple)


class AlbumScraper(Protocol):
    """Download an Arles (or similar) album URL into relative file tuples."""

    def scrape(
        self,
        url: str,
        headers: Optional[Mapping[str, str]] = None,
        sink: Any = None,
        output_dir: Optional[Path] = None,
    ) -> Any:
        ...


class UnavailableAlbumScraper:
    """Used when ``src.export.scrape`` is not installed yet."""

    def scrape(
        self,
        url: str,
        headers: Optional[Mapping[str, str]] = None,
        sink: Any = None,
    ) -> ScrapeResult:
        raise RuntimeError(
            "album scraper is not available (src.export.scrape missing)"
        )


def validate_scrape_url(url: str) -> str:
    stripped = str(url or "").strip()
    if not stripped:
        raise ValueError("url is required")
    parsed = urlparse(stripped)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be an http(s) URL")
    return stripped


def normalize_scrape_result(result: Any) -> ScrapeResult:
    if isinstance(result, ScrapeResult):
        files = tuple(_normalize_file(item) for item in result.files)
        urls = tuple(str(item) for item in result.gallery_urls if str(item).strip())
        return ScrapeResult(files=files, gallery_urls=urls)
    album_root = getattr(result, "album_root", None)
    if album_root is not None:
        urls_raw = (
            getattr(result, "child_gallery_urls", None)
            or getattr(result, "gallery_urls", None)
            or ()
        )
        return ScrapeResult(
            files=files_from_album_root(Path(album_root)),
            gallery_urls=tuple(str(item) for item in urls_raw if str(item).strip()),
        )
    if isinstance(result, dict):
        if result.get("album_root"):
            urls_raw = (
                result.get("child_gallery_urls")
                or result.get("gallery_urls")
                or result.get("urls")
                or ()
            )
            return ScrapeResult(
                files=files_from_album_root(Path(str(result["album_root"]))),
                gallery_urls=tuple(str(item) for item in urls_raw if str(item).strip()),
            )
        files_raw = result.get("files") or ()
        urls_raw = result.get("gallery_urls") or result.get("urls") or ()
        return ScrapeResult(
            files=tuple(_normalize_file(item) for item in files_raw),
            gallery_urls=tuple(str(item) for item in urls_raw if str(item).strip()),
        )
    files_attr = getattr(result, "files", None)
    if files_attr is not None:
        urls_attr = (
            getattr(result, "gallery_urls", None)
            or getattr(result, "child_urls", None)
            or getattr(result, "child_gallery_urls", None)
            or ()
        )
        return ScrapeResult(
            files=tuple(_normalize_file(item) for item in files_attr),
            gallery_urls=tuple(str(item) for item in urls_attr if str(item).strip()),
        )
    if isinstance(result, (list, tuple)):
        return ScrapeResult(
            files=tuple(_normalize_file(item) for item in result),
            gallery_urls=(),
        )
    raise TypeError(f"unsupported scrape result: {type(result)!r}")


def files_from_album_root(root: Path) -> Tuple[FileTuple, ...]:
    album = Path(root)
    if not album.is_dir():
        return ()
    files: List[FileTuple] = []
    for path in album.rglob("*"):
        if not path.is_file() or path.name in _STATE_NAMES:
            continue
        relpath = path.relative_to(album).as_posix()
        files.append((relpath, path.read_bytes(), path.stat().st_mtime))
    return tuple(files)


def should_spawn_preview_child(
    files: Sequence[FileTuple],
    gallery_urls: Sequence[str],
) -> bool:
    """Leaf albums get a preview child; parent index+subgallery pages do not."""
    if not files:
        return False
    rels = [str(item[0]).replace("\\", "/").lower() for item in files]
    has_media = any(
        part.startswith("hrimages/") or part.startswith("imagepages/")
        for part in rels
    )
    if has_media:
        return True
    return not gallery_urls


def _normalize_file(item: Any) -> FileTuple:
    if isinstance(item, (tuple, list)):
        if len(item) < 2:
            raise ValueError("scrape file must be (relpath, data[, mtime])")
        relpath = str(item[0])
        data = item[1]
        mtime_raw = item[2] if len(item) > 2 else None
        mtime = float(mtime_raw) if mtime_raw is not None else None
        if isinstance(data, Path):
            return relpath, data.read_bytes(), mtime
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("scrape file data must be bytes")
        return relpath, bytes(data), mtime
    relpath = str(getattr(item, "relpath"))
    data = getattr(item, "data", None)
    if data is None:
        data = getattr(item, "content", None)
    if isinstance(data, Path):
        data = data.read_bytes()
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("scrape file data must be bytes")
    mtime_raw = getattr(item, "last_modified", None)
    mtime = float(mtime_raw) if mtime_raw is not None else None
    return relpath, bytes(data), mtime


@dataclass
class _AdaptedScraper:
    inner: Any

    def scrape(
        self,
        url: str,
        headers: Optional[Mapping[str, str]] = None,
        sink: Any = None,
        output_dir: Optional[Path] = None,
    ) -> ScrapeResult:
        raw = _call_scrape(
            self.inner, url, headers=headers, sink=sink, output_dir=output_dir
        )
        return normalize_scrape_result(raw)


@dataclass
class _DirScraperAdapter:
    """Adapt ``scrape(ScrapeRequest, output_dir) -> album_root`` (export.scrape)."""

    inner: Any

    def scrape(
        self,
        url: str,
        headers: Optional[Mapping[str, str]] = None,
        sink: Any = None,
        output_dir: Optional[Path] = None,
    ) -> ScrapeResult:
        dest = Path(output_dir) if output_dir is not None else Path(
            tempfile.mkdtemp(prefix="arles-scrape-")
        )
        dest.mkdir(parents=True, exist_ok=True)
        request = _build_scrape_request(url, headers)
        if sink is not None:
            ops = getattr(sink, "ops", None)
            if callable(ops):
                try:
                    ops("Downloading album", stage="scrape", current=0, total=1)
                except Exception:
                    pass
        try:
            raw = self.inner.scrape(request, dest, sink=sink)
        except TypeError:
            raw = self.inner.scrape(request, dest)
        return normalize_scrape_result(raw)


def _call_scrape(
    scraper: Any,
    url: str,
    *,
    headers: Optional[Mapping[str, str]],
    sink: Any,
    output_dir: Optional[Path] = None,
) -> Any:
    try:
        return scraper.scrape(
            url, headers=headers, sink=sink, output_dir=output_dir
        )
    except TypeError:
        try:
            return scraper.scrape(url, headers=headers, sink=sink)
        except TypeError:
            try:
                return scraper.scrape(url, headers=headers)
            except TypeError:
                return scraper.scrape(url)


def _build_scrape_request(url: str, headers: Optional[Mapping[str, str]]) -> Any:
    try:
        from ..export.scrape.models import ScrapeRequest

        return ScrapeRequest(url=url, headers=dict(headers or {}))
    except ImportError:
        return {"url": url, "headers": dict(headers or {})}


def _scrape_writes_to_dir(scrape_fn: Any) -> bool:
    try:
        signature = inspect.signature(scrape_fn)
    except (TypeError, ValueError):
        return False
    names = [param.name for param in signature.parameters.values() if param.name != "self"]
    if not names:
        return False
    if names[0] == "request":
        return True
    return len(names) >= 2 and names[1] in {"output_dir", "dest"}


def wrap_scraper(scraper: Any) -> AlbumScraper:
    if scraper is None:
        return UnavailableAlbumScraper()
    if isinstance(scraper, type):
        scraper = scraper()
    if not hasattr(scraper, "scrape"):
        raise TypeError("scraper must provide scrape()")
    if type(scraper).__name__ == "ArlesGalleryScraper" or _scrape_writes_to_dir(
        scraper.scrape
    ):
        return _DirScraperAdapter(scraper)
    return _AdaptedScraper(scraper)


def load_default_scraper() -> AlbumScraper:
    """Prefer ``src.export.scrape.ArlesGalleryScraper`` when present."""
    specs: List[Tuple[str, str]] = [
        ("src.export.scrape", "ArlesGalleryScraper"),
        ("src.export.scrape.scraper", "ArlesGalleryScraper"),
        ("src.export.scrape", "get_scraper"),
        ("src.export.scrape", "AlbumScraper"),
        ("src.export.scrape.scraper", "ArlesAlbumScraper"),
        ("src.export.scrape.scraper", "AlbumScraper"),
    ]
    for module_name, attr in specs:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        value = getattr(module, attr, None)
        if value is None:
            continue
        try:
            if attr == "get_scraper" and callable(value):
                instance = value()
            elif isinstance(value, type):
                instance = value()
            else:
                instance = value
        except TypeError:
            continue
        if hasattr(instance, "scrape"):
            return wrap_scraper(instance)
    return UnavailableAlbumScraper()
