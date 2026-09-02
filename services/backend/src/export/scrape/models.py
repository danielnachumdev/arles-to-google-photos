"""Public scrape request/result types."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class ScrapeRequest:
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ScrapeResult:
    album_root: Path
    child_gallery_urls: Tuple[str, ...]
    gallery_title: Optional[str]
