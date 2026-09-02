from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DAY1_MINI = FIXTURES / "day1_mini"
DAY1_ARLES = FIXTURES / "day1_arles"
REPO_ROOT = Path(__file__).resolve().parents[3]

_JOBS_ROOT_ISOLATED = False


_LIVE_GCS = os.environ.get("ARLES_LIVE_GCS", "").strip().lower() in {
    "1",
    "true",
    "yes",
}


def _isolate_jobs_root() -> None:
    """Each xdist worker (and the controller) must use its own JOBS_ROOT.

    ``import src.api.app`` still runs ``app = create_app()``, which opens
    ``{JOBS_ROOT}/migrator.sqlite`` when DATABASE_URL is blank. Sharing that
    file across workers races on Linux (``database is locked``) and makes
    collection non-deterministic. Also clear remote DB / bucket envs so a
    developer Cloud SQL or GCS config cannot leak into unit tests.
    ``APP_ENV`` defaults to ``local`` here so factories use volume/fs + sqlite
    unless a test explicitly sets cloud.
    """
    global _JOBS_ROOT_ISOLATED
    if _JOBS_ROOT_ISOLATED:
        return
    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    os.environ["JOBS_ROOT"] = tempfile.mkdtemp(prefix=f"arles-jobs-{worker}-")
    os.environ["APP_ENV"] = "local"
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("SQLALCHEMY_DATABASE_URL", None)
    if not _LIVE_GCS:
        os.environ.pop("GCS_BUCKET", None)
        os.environ.pop("ARTIFACT_BUCKET", None)
    _JOBS_ROOT_ISOLATED = True


_isolate_jobs_root()


def pytest_configure(config: pytest.Config) -> None:
    _isolate_jobs_root()


def _optional_local_album() -> Path:
    data = REPO_ROOT / "data"
    if data.is_dir():
        for child in sorted(data.iterdir()):
            if (
                child.is_dir()
                and (child / "index.html").is_file()
                and (child / "hrimages").is_dir()
            ):
                return child
    return data / "Day1"


DAY1_REAL = _optional_local_album()


@pytest.fixture
def day1_mini() -> Path:
    return DAY1_MINI


@pytest.fixture
def day1_arles() -> Path:
    return DAY1_ARLES
