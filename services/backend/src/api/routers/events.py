"""SSE job events and persisted run-history."""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncIterator, Dict

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from ...jobs.events import AUDIENCE_UI, event_to_dict, filter_events_by_audience
from ...jobs.persistence.users import UserRecord
from ..deps import ApiDependencies, get_current_user, get_deps, require_job

router = APIRouter(prefix="/api/jobs", tags=["events"])

# event.stage is a progress log, not job.status. Ingest still terminates on the
# preview_ready *stage*; job status uses pending|running|done|failed|cancelled.
_EVENT_STAGE_TERMINALS = {"done", "error", "failed", "cancelled"}
_SSE_WAIT = ThreadPoolExecutor(max_workers=32, thread_name_prefix="sse-wait")


@router.get("/{job_id}/events")
def job_events(
    job_id: str,
    phase: str = Query(default="ingest"),
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> StreamingResponse:
    require_job(deps.store, job_id, owner_id=user.id)
    queue = deps.events.subscribe(job_id)
    terminal = set(_EVENT_STAGE_TERMINALS)
    if phase not in {"publish", "scrape"}:
        terminal.add("preview_ready")

    async def stream() -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        while True:
            event = await loop.run_in_executor(_SSE_WAIT, queue.get)
            yield f"data: {json.dumps(event_to_dict(event))}\n\n"
            if event.stage in terminal:
                break

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/{job_id}/history")
def job_history(
    job_id: str,
    audience: str = Query(default=AUDIENCE_UI),
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    job = require_job(deps.store, job_id, owner_id=user.id)
    wanted = (audience or AUDIENCE_UI).strip().lower()
    if wanted not in {AUDIENCE_UI, "ops", "all"}:
        wanted = AUDIENCE_UI
    return {
        "events": [
            event_to_dict(event)
            for event in filter_events_by_audience(job.events, wanted)
        ]
    }
