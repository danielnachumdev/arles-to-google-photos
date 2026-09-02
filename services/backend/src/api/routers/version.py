"""App version for the UI / ops checks."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from ...version import __version__

router = APIRouter(prefix="/api/version", tags=["version"])


@router.get("")
def get_version() -> Dict[str, Any]:
    return {"version": __version__}
