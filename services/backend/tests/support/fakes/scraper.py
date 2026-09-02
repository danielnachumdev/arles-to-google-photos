"""AlbumScraper strategy double: canned files / gallery URLs, never logs headers."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.progress import raise_if_cancelled
from tests.support.album import AlbumTree, FileTuple


def mini_album_files() -> List[FileTuple]:
    return AlbumTree.mini_tuples()


@dataclass
class FakeAlbumScraper:
    """In-memory scraper implementing the jobs AlbumScraper Protocol."""

    files: Sequence[FileTuple] = field(default_factory=mini_album_files)
    gallery_urls: Sequence[str] = ()
    by_url: Dict[str, "FakeAlbumScraper"] = field(default_factory=dict)
    error: Optional[BaseException] = None
    calls: List[Dict[str, Any]] = field(default_factory=list)
    hold: Optional[threading.Event] = None
    started: Optional[threading.Event] = None

    def scrape(
        self,
        url: str,
        headers: Optional[Mapping[str, str]] = None,
        sink: Any = None,
        output_dir: Optional[Path] = None,
    ) -> Any:
        del output_dir
        self.calls.append({"url": url, "header_names": list((headers or {}).keys())})
        override = self.by_url.get(url)
        if override is not None and override is not self:
            return override.scrape(
                url, headers=headers, sink=sink, output_dir=None
            )
        if sink is not None:
            sink.emit("scrape", f"Fetching gallery index: {url}", current=0, total=0)
        if self.started is not None:
            self.started.set()
        if self.hold is not None:
            while not self.hold.wait(timeout=0.05):
                raise_if_cancelled(sink)
        raise_if_cancelled(sink)
        if self.error is not None:
            raise self.error
        files = list(self.files)
        total = len(files)
        if sink is not None:
            for index, (relpath, _data, _mtime) in enumerate(files, start=1):
                raise_if_cancelled(sink)
                sink.emit("scrape", relpath, current=index, total=total)
            sink.emit(
                "scrape",
                "Download complete",
                current=max(total, 1),
                total=max(total, 1),
            )
        from src.jobs.scraper import ScrapeResult

        return ScrapeResult(
            files=files,
            gallery_urls=list(self.gallery_urls),
        )
