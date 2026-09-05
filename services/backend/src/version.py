"""Released product version and image build stamp for Arles Migrator (API + UI)."""
from __future__ import annotations

import os
from pathlib import Path

__version__ = "1.0.0"

# Written at image build (see Dockerfiles). Prefer env; fall back to stamp file.
_BUILD_TIME_FILE = Path("/etc/arles-build-time")


def _resolve_build_time() -> str:
    env = (os.environ.get("BUILD_TIME") or "").strip()
    if env:
        return env
    try:
        return _BUILD_TIME_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


BUILD_TIME = _resolve_build_time()
