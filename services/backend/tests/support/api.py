"""Declarative FastAPI client for job ingest / scrape / publish / wait."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi.testclient import TestClient

from tests.support.album import AlbumTree
from tests.support.fakes.publisher import fake_publisher
from tests.support.fakes.scraper import FakeAlbumScraper
from tests.support.waits import JobWaiter


class MigratorApi:
    """Thin wrapper: create_app + TestClient + common job operations."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        scraper: Any = None,
        publisher: Any = None,
        gp_factory: Any = None,
        state_backend: Optional[str] = None,
        product_url: str = "https://photos.example/album-1",
        with_scraper: bool = False,
        waiter: Optional[JobWaiter] = None,
    ) -> None:
        from unittest.mock import MagicMock

        from src.api.app import create_app

        self.tmp_path = tmp_path
        self.jobs_root = tmp_path / "jobs"
        self.publisher = (
            publisher if publisher is not None else fake_publisher(product_url=product_url)
        )
        self.gp_factory = (
            gp_factory
            if gp_factory is not None
            else MagicMock(return_value=MagicMock(name="GooglePhotos"))
        )
        self.scraper = scraper
        kwargs: dict[str, Any] = {
            "jobs_root": self.jobs_root,
            "publisher": self.publisher,
            "gp_factory": self.gp_factory,
        }
        if scraper is not None or with_scraper:
            self.scraper = scraper if scraper is not None else FakeAlbumScraper()
            kwargs["scraper"] = self.scraper
        if state_backend is not None:
            kwargs["state_backend"] = state_backend
        self.app = create_app(**kwargs)
        self.client = TestClient(self.app)
        self.waiter = waiter or JobWaiter()

    def ingest(
        self,
        files: list | None = None,
        *,
        overwrite: bool = False,
        auto_publish: bool = False,
        token: str | None = None,
        timeout: float = 8.0,
        wait: bool = True,
        expected_status: int = 201,
    ) -> dict:
        params: list[str] = []
        if overwrite:
            params.append("overwrite=true")
        if auto_publish:
            params.append("auto_publish=true")
        query = f"?{'&'.join(params)}" if params else ""
        data = {"access_token": token} if token else None
        response = self.client.post(
            f"/api/jobs{query}",
            files=files or AlbumTree.mini_multipart(),
            data=data,
        )
        if expected_status != 201:
            assert response.status_code == expected_status, response.text
            return response.json() if response.content else {}
        assert response.status_code == 201, response.text
        body = response.json()
        if not wait:
            return body
        return self.wait_job(
            body["id"],
            timeout=timeout,
            last_stages=("preview_ready", "done"),
        )

    def wait_job(
        self,
        job_id: str,
        *,
        status: str = "done",
        last_stage: str | None = None,
        last_stages: tuple[str, ...] | set[str] | frozenset[str] | None = None,
        timeout: float = 8.0,
    ) -> dict:
        return self.waiter.http_status(
            self.client,
            job_id,
            status=status,
            last_stage=last_stage,
            last_stages=last_stages,
            timeout=timeout,
        )

    def publish(self, job_id: str, token: str = "ya29.test-token"):
        return self.client.post(
            f"/api/jobs/{job_id}/publish",
            json={"access_token": token},
        )

    def scrape(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        auto_publish: bool = False,
        token: str | None = None,
        wait: bool = False,
        status: str = "done",
        timeout: float = 8.0,
    ) -> dict:
        payload: dict[str, Any] = {"url": url}
        if headers:
            payload["headers"] = headers
        if auto_publish:
            payload["auto_publish"] = True
        if token is not None:
            payload["access_token"] = token
        response = self.client.post("/api/jobs/scrape", json=payload)
        assert response.status_code == 201, response.text
        body = response.json()
        if not wait:
            return body
        return self.wait_job(body["id"], status=status, timeout=timeout)
