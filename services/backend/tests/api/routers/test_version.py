"""GET /api/version returns the released product version and image build time."""
from __future__ import annotations

from pathlib import Path

from tests.support.api import MigratorApi

from src.version import BUILD_TIME, __version__


def test_get_version(tmp_path: Path) -> None:
    client = MigratorApi(tmp_path).client
    response = client.get("/api/version")
    assert response.status_code == 200
    assert response.json() == {"version": __version__, "build_time": BUILD_TIME or None}
    assert __version__ == "1.0.0"


def test_get_version_includes_build_time_when_set(
    tmp_path: Path, monkeypatch: object
) -> None:
    import src.api.routers.version as version_router
    import src.version as version_mod

    stamp = "2026-09-05T14:23:00Z"
    monkeypatch.setattr(version_mod, "BUILD_TIME", stamp)
    monkeypatch.setattr(version_router, "BUILD_TIME", stamp)
    client = MigratorApi(tmp_path).client
    response = client.get("/api/version")
    assert response.status_code == 200
    assert response.json() == {"version": __version__, "build_time": stamp}
