"""Request-scoped accessors for services stored on ``app.state``."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request

from ..export.editor import PreviewEditor
from ..export.preview import AlbumPreview
from ..jobs.cancel import CancelService
from ..jobs.events import JobEventBus
from ..jobs.ingest import IngestService
from ..jobs.orchestrator import JobOrchestrator
from ..jobs.persistence import resolve_app_env
from ..jobs.persistence.auth import IdentityError, resolve_request_email
from ..jobs.persistence.users import UserRecord, UserStore
from ..jobs.publish import PublishService
from ..jobs.reprocess import ReprocessService
from ..jobs.restart import RestartService
from ..jobs.scrape import ScrapeService
from ..jobs.store import Job, JobNotFoundError, JobStore


@dataclass(frozen=True)
class ApiDependencies:
    store: JobStore
    ingest: IngestService
    publish: PublishService
    reprocess: ReprocessService
    scrape: ScrapeService
    restart: RestartService
    cancel: CancelService
    editor: PreviewEditor
    events: JobEventBus
    jobs_root: Path
    orchestrator: JobOrchestrator


def get_deps(request: Request) -> ApiDependencies:
    deps = getattr(request.app.state, "deps", None)
    if not isinstance(deps, ApiDependencies):
        raise RuntimeError("API dependencies are not configured")
    return deps


def get_current_user(request: Request) -> UserRecord:
    """Upsert the oauth identity into ``users`` and return it (per request)."""
    cached = getattr(request.state, "current_user", None)
    if isinstance(cached, UserRecord):
        return cached
    deps = get_deps(request)
    try:
        email = resolve_request_email(
            request.headers,
            app_env=resolve_app_env(),
        )
    except IdentityError as exc:
        raise HTTPException(status_code=401, detail="authentication required") from exc

    state = deps.store._state
    if state is None:
        raise HTTPException(status_code=503, detail="state backend unavailable")
    # Json backend has no users table — synthesize a stable local user.
    from ..jobs.persistence.json_state import JsonStateStore
    from ..jobs.persistence.sqlalchemy_state import SqlAlchemyStateStore

    if isinstance(state, SqlAlchemyStateStore):
        user = UserStore(state).upsert_email(email)
    elif isinstance(state, JsonStateStore):
        user = UserRecord(
            id=f"json:{email}",
            email=email,
            created_at="1970-01-01T00:00:00+00:00",
        )
    else:
        raise HTTPException(status_code=503, detail="unsupported state backend")
    request.state.current_user = user
    return user


def require_job(
    store: JobStore,
    job_id: str,
    *,
    owner_id: Optional[str] = None,
) -> Job:
    try:
        return store.get(job_id, owner_id=owner_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc


def require_preview(job: Job) -> AlbumPreview:
    if job.preview is None:
        raise HTTPException(status_code=409, detail="preview not ready")
    return job.preview
