"""Orchestrator settings: max concurrent running jobs."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ..deps import ApiDependencies, get_deps
from ..schemas import OrchestratorSettingsBody

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(deps: ApiDependencies = Depends(get_deps)) -> Dict[str, Any]:
    snap = deps.orchestrator.snapshot()
    return {
        "max_concurrent_jobs": snap["max_concurrent_jobs"],
        "pending": snap["pending"],
        "running": snap["running"],
        "waiting": snap["waiting"],
    }


@router.patch("")
def patch_settings(
    body: OrchestratorSettingsBody,
    deps: ApiDependencies = Depends(get_deps),
) -> Dict[str, Any]:
    try:
        deps.orchestrator.set_max_concurrent(body.max_concurrent_jobs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_settings(deps)
