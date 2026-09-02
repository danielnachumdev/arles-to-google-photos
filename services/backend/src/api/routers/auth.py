"""OAuth config for frontend Google Photos sign-in."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..google_oauth import load_google_oauth_client_id, photos_scope_list

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/config")
def auth_config() -> Dict[str, Any]:
    client_id = load_google_oauth_client_id()
    if client_id is None:
        raise HTTPException(
            status_code=503,
            detail="google oauth client is not configured",
        )
    return {"client_id": client_id, "scopes": photos_scope_list()}
