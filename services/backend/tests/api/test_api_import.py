"""Importing API submodules must not open the default JOBS_ROOT sqlite."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_google_oauth_import_does_not_create_sqlite(tmp_path: Path) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["JOBS_ROOT"] = str(tmp_path)
    extra = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{backend_root}{os.pathsep}{extra}" if extra else str(backend_root)
    )
    subprocess.run(
        [sys.executable, "-c", "from src.api.google_oauth import photos_scope_list"],
        cwd=str(backend_root),
        env=env,
        check=True,
    )
    assert not (tmp_path / "migrator.sqlite").exists()
