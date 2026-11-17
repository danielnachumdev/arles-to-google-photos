"""App version / build stamp for the UI / ops checks."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter

from ...version import BUILD_TIME, resolved_version

router = APIRouter(prefix="/api/version", tags=["version"])


@router.get("")
def get_version() -> Dict[str, Any]:
    build_time: Optional[str] = BUILD_TIME or None
    return {"version": resolved_version(), "build_time": build_time}
