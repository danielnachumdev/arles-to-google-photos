"""GET /api/version returns the released product version."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.version import __version__


def test_get_version(tmp_path: Path) -> None:
    app = create_app(jobs_root=tmp_path, state_backend="json")
    client = TestClient(app)
    response = client.get("/api/version")
    assert response.status_code == 200
    assert response.json() == {"version": __version__}
    assert __version__ == "1.0.0"
