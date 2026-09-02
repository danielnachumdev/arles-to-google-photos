"""Publish a preview (or prior upload) as a new independent upload job."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ...jobs.persistence.users import UserRecord
from ..deps import ApiDependencies, get_current_user, get_deps, require_job
from ..schemas import PublishBody

router = APIRouter(prefix="/api/jobs", tags=["publish"])


@router.post("/{job_id}/publish", status_code=201)
def publish_job(
    job_id: str,
    body: PublishBody,
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    """Start a new upload job from ``job_id`` (preview or prior upload snapshot).

    Returns the upload job immediately (pending until a worker slot is free).
    ``finish`` runs via the orchestrator. Subscribe to
    ``/api/jobs/{upload_id}/events?phase=publish``, not the preview id.
    """
    require_job(deps.store, job_id, owner_id=user.id)
    try:
        upload_id = deps.publish.start(job_id, access_token=body.access_token)
    except ValueError as exc:
        detail = str(exc)
        if detail == "google access token required":
            status = 401
        elif detail in {
            "preview not ready",
            "publish already in progress",
        }:
            status = 409
        else:
            status = 400
        raise HTTPException(status_code=status, detail=detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    token = body.access_token
    deps.orchestrator.submit(
        upload_id,
        lambda: deps.publish.finish(upload_id, access_token=token),
    )
    return deps.store.detail_dict(upload_id, owner_id=user.id)
