"""API: POST /api/jobs/validate creates a TYPE_VALIDATE job."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.export.validate.models import (
    PhotosAlbumSnapshot,
    PhotosItemSnapshot,
    RemoteAlbumSnapshot,
    RemoteItemSnapshot,
)
from src.jobs.store import TYPE_VALIDATE
from tests.support.waits import JobWaiter


class _FakeDiscovery:
    def discover(
        self,
        root_url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        sink: Any = None,
    ) -> Tuple[List[RemoteAlbumSnapshot], List[str]]:
        return (
            [
                RemoteAlbumSnapshot(
                    title_id="Demo",
                    title="Demo",
                    url=root_url,
                    items=(
                        RemoteItemSnapshot(
                            item_id="img1", caption="hi", byte_size=42
                        ),
                    ),
                )
            ],
            [],
        )


class _FakePhotos:
    def index(
        self, gp: Any, *, sink: Any = None
    ) -> Tuple[List[PhotosAlbumSnapshot], List[str]]:
        return (
            [
                PhotosAlbumSnapshot(
                    title_id="Demo",
                    title="Demo",
                    album_id="alb-demo",
                    product_url="https://photos.example/alb-demo",
                    items=(
                        PhotosItemSnapshot(
                            item_id="img1",
                            filename="img1",
                            caption="hi",
                            byte_size=42,
                        ),
                    ),
                )
            ],
            [],
        )


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("APP_ENV", "local")
    app = create_app(jobs_root=tmp_path, state_backend="json")
    validate = app.state.deps.validate
    assert validate is not None
    validate._discovery = _FakeDiscovery()
    validate._photos = _FakePhotos()
    validate._gp_factory = lambda _token: object()
    return TestClient(app)


def test_validate_requires_token(client: TestClient) -> None:
    response = client.post(
        "/api/jobs/validate",
        json={"url": "https://example.com/gallery/index.html", "access_token": ""},
    )
    assert response.status_code == 401


def test_validate_runs_and_persists_report(client: TestClient) -> None:
    response = client.post(
        "/api/jobs/validate",
        json={
            "url": "https://example.com/gallery/index.html",
            "access_token": "ya29.demo",
            "headers": {"Cookie": "session=1"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == TYPE_VALIDATE
    detail = JobWaiter(timeout=5.0).http_status(
        client, body["id"], status="done", last_stages=("done",)
    )
    report = detail.get("validation_report")
    assert isinstance(report, dict)
    assert report["identical"] is True
    assert report["summary"]["matched"] == 1
