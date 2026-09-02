"""HTTP / MigratorApi suites. Not collected (no Test prefix)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest

from tests.support.api import MigratorApi
from tests.support.fakes.scraper import FakeAlbumScraper
from tests.support.suites.tmp import TmpPathSuite


class ApiClientSuite(TmpPathSuite):
    """HTTP tests sharing a MigratorApi under ``tmp_path / jobs``.

    ``setup_method`` builds ``self.api`` / ``self.client`` / ``self.store``.
    Override ``api_kwargs`` or call ``make_api(...)`` for a custom client.
    """

    with_scraper: bool = False
    product_url: str = "https://photos.example/album-1"
    state_backend: Optional[str] = None

    def api_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"product_url": self.product_url}
        if self.with_scraper:
            kwargs["with_scraper"] = True
            scraper = getattr(self, "scraper", None)
            if scraper is not None:
                kwargs["scraper"] = scraper
        if self.state_backend is not None:
            kwargs["state_backend"] = self.state_backend
        return kwargs

    def make_api(self, tmp_path: Path | None = None, **kwargs: object) -> MigratorApi:
        path = tmp_path if tmp_path is not None else self.tmp_path
        merged = {**self.api_kwargs(), **kwargs}
        api = MigratorApi(path, **merged)  # type: ignore[arg-type]
        self.api = api
        self.client = api.client
        self.jobs_root = api.jobs_root
        self.store = api.app.state.deps.store
        self.waiter = api.waiter
        return api


class ScrapeFakeSuite(ApiClientSuite):
    """HTTP scrape tests with an in-memory FakeAlbumScraper."""

    with_scraper = True
    product_url = "https://photos.example/scrape-album"

    @pytest.fixture(autouse=True)
    def _bind_scraper(self) -> None:
        self.scraper = FakeAlbumScraper()
