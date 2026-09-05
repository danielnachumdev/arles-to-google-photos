"""Job CRUD, media, and reprocess routes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from starlette.datastructures import FormData

from ...export.editor import PreviewEdits
from ...export.media_kinds import (
    BROWSER_PLAYABLE_VIDEO,
    KIND_IMAGE,
    infer_item_kind,
)
from ...export.preview import AlbumJournal, PreviewItem
from ...jobs.ingest import AlbumExistsError
from ...jobs.persistence.users import UserRecord
from ...jobs.reprocess import (
    REPROCESS_MODE_NEW,
    job_is_web_origin,
    leaf_scrape_id_for_reprocess,
    resolve_title_prefix,
    start_new_preview_reprocess,
)
from ...jobs.restart import JobNotRestartableError
from ...jobs.store import (
    STATUS_PENDING,
    TYPE_PREVIEW,
    TYPE_SCRAPE,
    TYPE_UPLOAD,
    JobNotArchivableError,
    JobNotCancellableError,
    JobNotFoundError,
)
from ...jobs.upload_ingress import AlbumUploadPart, MultipartAlbumIngress
from ..deps import (
    ApiDependencies,
    get_current_user,
    get_deps,
    require_job,
    require_preview,
)
from ..schemas import PreviewEditBody, ReprocessBody, RestartBody

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# Starlette defaults are 1000 (DoS guard). Large Arles hubs exceed that; raise
# for album ingest only (parsed via request.form, not File()/Form() defaults).
MULTIPART_MAX_FILES = 10_000
MULTIPART_MAX_FIELDS = 10_000
NDJSON_ACCEPT = "application/x-ndjson"


async def _album_upload_form(request: Request) -> FormData:
    return await request.form(
        max_files=MULTIPART_MAX_FILES,
        max_fields=MULTIPART_MAX_FIELDS,
    )


def _form_uploads(form: FormData) -> List[UploadFile]:
    uploads: List[UploadFile] = []
    for item in form.getlist("files"):
        # Duck-type: TestClient / Starlette may not match fastapi.UploadFile isinstance.
        if hasattr(item, "filename") and hasattr(item, "file"):
            uploads.append(item)  # type: ignore[arg-type]
    return uploads


def _form_optional_str(form: FormData, key: str) -> Optional[str]:
    raw = form.get(key)
    if raw is None or hasattr(raw, "filename"):
        return None
    return str(raw)


def _wants_ndjson_progress(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return NDJSON_ACCEPT in accept


def _album_parts_from_form(form: FormData) -> List[AlbumUploadPart]:
    files = _form_uploads(form)
    if not files:
        raise HTTPException(status_code=400, detail="files required")
    mtimes = [
        None if hasattr(value, "filename") else value
        for value in form.getlist("lastModified")
    ]
    parts: List[AlbumUploadPart] = []
    for index, upload in enumerate(files):
        raw_mtime = mtimes[index] if index < len(mtimes) else None
        stamp: Optional[float] = None
        if raw_mtime:
            stamp = float(raw_mtime) / 1000.0
        parts.append(
            AlbumUploadPart(
                relpath=upload.filename or "",
                stream=upload.file,
                mtime=stamp,
            )
        )
    return parts


def _album_exists_http(exc: AlbumExistsError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "album_exists",
            "existing_id": exc.existing_id,
            "title": exc.title,
        },
    )


@router.post("", status_code=201, response_model=None)
async def create_job(
    request: Request,
    overwrite: bool = Query(False),
    auto_publish: bool = Query(False),
    form: FormData = Depends(_album_upload_form),
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Any:
    """Ingest an uploaded album tree.

    ``overwrite`` defaults to false. Same gallery title without overwrite → 409
    ``{"detail": {"code": "album_exists", "existing_id": "...", "title": "..."}}``.
    ``overwrite=true`` folds into the existing job (keeps id / created_at /
    product_url).

    Each multipart part is streamed into durable storage one file at a time
    (no full album staging tree on local disk). With
    ``Accept: application/x-ndjson``, the response streams ``store`` progress
    lines then a final ``done`` event with the job; otherwise a single JSON job
    body is returned after storage completes. Preview prep is always enqueued
    on the job orchestrator before the response finishes.
    """
    parts = _album_parts_from_form(form)
    access_token = _form_optional_str(form, "access_token")
    if auto_publish and not (access_token or "").strip():
        raise HTTPException(
            status_code=400, detail="google access token required"
        )
    ingress = MultipartAlbumIngress(
        store=deps.store,
        ingest=deps.ingest,
        jobs_root=deps.jobs_root,
        submit=deps.orchestrator.submit,
        events_emit=deps.events.emit,
    )
    if not _wants_ndjson_progress(request):
        try:
            job_id = ingress.ingest(
                parts,
                overwrite=overwrite,
                auto_publish=auto_publish,
                access_token=access_token,
                owner_id=user.id,
            )
        except AlbumExistsError as exc:
            raise _album_exists_http(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return deps.store.detail_dict(job_id, owner_id=user.id)

    events = ingress.iter_ingest(
        parts,
        overwrite=overwrite,
        auto_publish=auto_publish,
        access_token=access_token,
        owner_id=user.id,
    )
    try:
        first = next(events)
    except AlbumExistsError as exc:
        raise _album_exists_http(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StopIteration as exc:
        raise HTTPException(status_code=500, detail="empty ingest") from exc

    def _done_line(job_id: str) -> str:
        detail = deps.store.detail_dict(job_id, owner_id=user.id)
        return json.dumps({"event": "done", "job": detail}) + "\n"

    def _ndjson_body() -> Iterator[str]:
        if first.get("event") == "complete":
            yield _done_line(str(first.get("job_id") or ""))
            return
        yield json.dumps(first) + "\n"
        job_id: Optional[str] = (
            str(first.get("job_id")) if first.get("job_id") else None
        )
        try:
            for event in events:
                if event.get("event") == "complete":
                    yield _done_line(str(event.get("job_id") or job_id or ""))
                    return
                yield json.dumps(event) + "\n"
            if job_id:
                yield _done_line(job_id)
        except AlbumExistsError as exc:
            yield json.dumps(
                {
                    "event": "error",
                    "detail": {
                        "code": "album_exists",
                        "existing_id": exc.existing_id,
                        "title": exc.title,
                    },
                }
            ) + "\n"
        except Exception as exc:
            yield json.dumps({"event": "error", "detail": str(exc)}) + "\n"

    return StreamingResponse(
        _ndjson_body(),
        media_type=NDJSON_ACCEPT,
        status_code=201,
    )


@router.get("")
def list_jobs(
    dedupe: bool = Query(False),
    include_archived: bool = Query(False),
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    """List jobs newest-first.

    Default: every non-archived run (preview + upload + scrape).
    ``?dedupe=true`` is one row per gallery title for the album library
    (preview/upload with a real title; scrape-only hostname rows are omitted).
    Dedupe ignores ``archived_at`` so Saved albums stay visible after Hide.
    ``?include_archived=true`` includes soft-deleted runs on the jobs list only.
    """
    if dedupe:
        return {"jobs": deps.store.list_album_summaries(owner_id=user.id)}
    return {
        "jobs": deps.store.list_summaries(
            include_archived=include_archived, owner_id=user.id
        )
    }


@router.get("/{job_id}")
def get_job(
    job_id: str,
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    require_job(deps.store, job_id, owner_id=user.id)
    return deps.store.detail_dict(job_id, owner_id=user.id)


@router.get("/{job_id}/children")
def list_job_children(
    job_id: str,
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    require_job(deps.store, job_id, owner_id=user.id)
    return {"jobs": deps.store.list_child_summaries(job_id)}


@router.get("/{job_id}/cancel-preview")
def cancel_preview(
    job_id: str,
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    """Summaries of non-terminal descendants that cancel would also stop."""
    require_job(deps.store, job_id, owner_id=user.id)
    return deps.store.cancel_preview_dict(job_id)


@router.get("/{job_id}/restart-preview")
def restart_preview(
    job_id: str,
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    """Scrape children split into done vs remaining for a cancelled restart."""
    require_job(deps.store, job_id, owner_id=user.id)
    try:
        return deps.restart.preview(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except JobNotRestartableError as exc:
        raise HTTPException(
            status_code=409, detail="job is not cancelled"
        ) from exc


@router.post("/{job_id}/archive")
def archive_job(
    job_id: str,
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    """Soft-delete a terminal job (and descendants). Artifacts stay."""
    require_job(deps.store, job_id, owner_id=user.id)
    try:
        archived_ids = deps.store.archive(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except JobNotArchivableError as exc:
        offending = str(exc)
        detail = (
            "job is still active"
            if offending == job_id
            else "descendant is still active"
        )
        raise HTTPException(status_code=409, detail=detail) from exc
    return {
        "job": deps.store.detail_dict(job_id, owner_id=user.id),
        "archived_ids": archived_ids,
    }


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str,
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    """Request cooperative cancel for a pending or running job."""
    require_job(deps.store, job_id, owner_id=user.id)
    try:
        deps.cancel.cancel(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except JobNotCancellableError as exc:
        raise HTTPException(
            status_code=409, detail="job already finished"
        ) from exc
    return deps.store.detail_dict(job_id, owner_id=user.id)


@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: str,
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> None:
    require_job(deps.store, job_id, owner_id=user.id)
    try:
        deps.store.delete(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc


@router.patch("/{job_id}")
def patch_job(
    job_id: str,
    body: PreviewEditBody,
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    job = require_job(deps.store, job_id, owner_id=user.id)
    preview = require_preview(job)
    try:
        journal = None
        if body.journal is not None:
            journal = AlbumJournal(
                heading=body.journal.heading,
                paragraphs=tuple(body.journal.paragraphs),
            )
        updated = deps.editor.apply(
            preview,
            PreviewEdits(
                title=body.title,
                description=body.description,
                journal=journal,
                captions=body.captions,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    deps.store.update_preview(job_id, updated)
    return deps.store.detail_dict(job_id, owner_id=user.id)


_MEDIA_VARIANTS = frozenset({"original", "thumb", "play"})


@router.get("/{job_id}/media/{item_id}")
def get_media(
    job_id: str,
    item_id: str,
    variant: str = Query("original"),
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> FileResponse:
    job = require_job(deps.store, job_id, owner_id=user.id)
    preview = require_preview(job)
    chosen = (variant or "original").strip().lower()
    if chosen not in _MEDIA_VARIANTS:
        raise HTTPException(status_code=400, detail="invalid media variant")
    for item in preview.items:
        if item.id != item_id:
            continue
        if chosen == "thumb":
            from ...export.thumbnail import ThumbnailRenderer

            try:
                path = ThumbnailRenderer(deps.store).ensure_thumb(
                    job_id,
                    item_id=item.id,
                    original_relpath=item.relpath,
                    thumb_relpath=item.thumb_relpath,
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail="media missing") from exc
            if not path.is_file():
                raise HTTPException(status_code=404, detail="media missing")
            return FileResponse(path, media_type="image/jpeg")
        relpath = _media_relpath(item, chosen)
        if relpath is None:
            raise HTTPException(status_code=404, detail="media missing")
        try:
            path = deps.store.ensure_artifact_file(job_id, relpath)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="media missing") from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="media missing")
        return FileResponse(path)
    raise HTTPException(status_code=404, detail="item not found")


def _media_relpath(item: PreviewItem, variant: str) -> Optional[str]:
    if variant == "original":
        return item.relpath
    kind = infer_item_kind(item.relpath, item.kind)
    if variant == "thumb":
        # Thumbnails are resolved via ThumbnailRenderer (never fall back to HR).
        return item.thumb_relpath
    if item.play_relpath:
        return item.play_relpath
    if kind == KIND_IMAGE:
        return item.relpath
    if Path(item.relpath).suffix.lower() in BROWSER_PLAYABLE_VIDEO:
        return item.relpath
    return None


@router.post("/{job_id}/restart", status_code=201)
def restart_job(
    job_id: str,
    body: RestartBody = Body(default_factory=RestartBody),
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    """Start a new job from a cancelled run. The cancelled job is unchanged."""
    require_job(deps.store, job_id, owner_id=user.id)
    try:
        new_id = deps.restart.restart(
            job_id,
            access_token=body.access_token,
            mode=body.mode,
        )
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except JobNotRestartableError as exc:
        raise HTTPException(
            status_code=409, detail="job is not cancelled"
        ) from exc
    except ValueError as exc:
        detail = str(exc)
        status = 401 if detail == "google access token required" else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return deps.store.detail_dict(new_id, owner_id=user.id)


@router.post("/{job_id}/reprocess")
def reprocess_job(
    job_id: str,
    body: Optional[ReprocessBody] = None,
    deps: ApiDependencies = Depends(get_deps),
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    job = require_job(deps.store, job_id, owner_id=user.id)
    payload = body or ReprocessBody()
    try:
        if job.type == TYPE_SCRAPE:
            deps.orchestrator.submit(job_id, lambda: deps.scrape.retry(job_id))
            return deps.store.detail_dict(job_id, owner_id=user.id)
        if job.type == TYPE_UPLOAD:
            raise ValueError("reprocess is only for preview jobs")
        if payload.mode == REPROCESS_MODE_NEW:
            new_id = start_new_preview_reprocess(
                deps.store,
                deps.jobs_root,
                job,
                title_prefix=resolve_title_prefix(payload.title_prefix),
                submit=deps.orchestrator.submit,
                reprocess=deps.reprocess,
                scrape=deps.scrape,
            )
            return deps.store.detail_dict(new_id, owner_id=user.id)
        if job_is_web_origin(job):
            scrape_id = leaf_scrape_id_for_reprocess(deps.store, job)
            if not scrape_id:
                raise ValueError("scrape url missing")
            if job.status != STATUS_PENDING:
                deps.store.set_status(
                    job_id, STATUS_PENDING, job_type=TYPE_PREVIEW
                )
            deps.orchestrator.submit(
                scrape_id, lambda: deps.scrape.retry(scrape_id)
            )
        else:
            if job.status != STATUS_PENDING:
                deps.store.set_status(
                    job_id, STATUS_PENDING, job_type=TYPE_PREVIEW
                )
            deps.orchestrator.submit(
                job_id, lambda: deps.reprocess.reprocess(job_id)
            )
    except ValueError as exc:
        detail = str(exc)
        status = 409 if detail == "reprocess is only for preview jobs" else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return deps.store.detail_dict(job_id, owner_id=user.id)
