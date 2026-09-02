"""Start a scrape/import job from a remote album URL."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ...jobs.persistence.users import UserRecord
from ..deps import ApiDependencies, get_current_user, get_deps
from ..schemas import ScrapeBody

router = APIRouter(prefix="/api/jobs", tags=["scrape"])


@router.post("/scrape", status_code=201)
def create_scrape_job(
    body: ScrapeBody,
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    """Create a scrape job as pending and enqueue finish under the orchestrator."""
    if body.auto_publish and not (body.access_token or "").strip():
        raise HTTPException(
            status_code=400, detail="google access token required"
        )
    try:
        job_id = deps.scrape.start(
            body.url,
            headers=body.headers or {},
            auto_publish=body.auto_publish,
            access_token=body.access_token,
            owner_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    deps.orchestrator.submit(job_id, lambda: deps.scrape.finish(job_id))
    return deps.store.detail_dict(job_id, owner_id=user.id)
