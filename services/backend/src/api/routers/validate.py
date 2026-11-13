"""Start a manual remote-vs-Photos validation job."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ...jobs.persistence.users import UserRecord
from ..deps import ApiDependencies, get_current_user, get_deps
from ..schemas import ValidateBody

router = APIRouter(prefix="/api/jobs", tags=["validate"])


@router.post("/validate", status_code=201)
def create_validate_job(
    body: ValidateBody,
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    """Create a validate job as pending and enqueue finish under the orchestrator."""
    if deps.validate is None:
        raise HTTPException(status_code=503, detail="validate service unavailable")
    try:
        job_id = deps.validate.start(
            body.url,
            headers=body.headers or {},
            access_token=body.access_token,
            owner_id=user.id,
        )
    except ValueError as exc:
        detail = str(exc)
        status = 401 if detail == "google access token required" else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    token = body.access_token
    deps.orchestrator.submit(
        job_id,
        lambda: deps.validate.finish(job_id, access_token=token),
    )
    return deps.store.detail_dict(job_id, owner_id=user.id)
