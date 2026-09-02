"""Pure Arles HTML gallery scraper (no JobStore / FastAPI)."""
from .client import (
    DEFAULT_USER_AGENT,
    FetchError,
    FetchedResource,
    HttpClient,
    UrllibHttpClient,
    merge_headers,
)
from .detect import (
    ArlesPageInfo,
    ArlesPageKind,
    GalleryItemRef,
    detect_arles_page,
    video_embed_urls,
)
from .models import ScrapeRequest, ScrapeResult
from .scraper import (
    ArlesGalleryScraper,
    FileScrapeResult,
    JobsAlbumScraper,
    NotArlesGalleryError,
    ScrapeEmptyError,
    ScrapeFetchError,
    get_scraper,
    scrape_arles_gallery,
)

__all__ = [
    "ArlesGalleryScraper",
    "ArlesPageInfo",
    "ArlesPageKind",
    "DEFAULT_USER_AGENT",
    "FetchError",
    "FetchedResource",
    "FileScrapeResult",
    "GalleryItemRef",
    "HttpClient",
    "JobsAlbumScraper",
    "NotArlesGalleryError",
    "ScrapeEmptyError",
    "ScrapeFetchError",
    "ScrapeRequest",
    "ScrapeResult",
    "UrllibHttpClient",
    "detect_arles_page",
    "get_scraper",
    "video_embed_urls",
    "merge_headers",
    "scrape_arles_gallery",
]
