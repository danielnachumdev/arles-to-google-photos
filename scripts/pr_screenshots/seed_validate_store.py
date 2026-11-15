#!/usr/bin/env python3
"""Seed a PII-safe validate job into the local JobStore (run inside the backend container).

Usage (from host via seed_demo.py):
  docker compose cp scripts/pr_screenshots/seed_validate_store.py backend:/tmp/seed_validate_store.py
  docker compose exec -T backend python /tmp/seed_validate_store.py

Env:
  JOBS_ROOT                 default /app/data/jobs
  ARLES_DEMO_VALIDATE_URL   default https://example.com/gallery/
  ARLES_DEMO_STATE          optional path inside container to merge ids into
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.api.app import create_app
from src.jobs.events import AUDIENCE_UI, KIND_LOG, KIND_PROGRESS, JobEvent
from src.jobs.store import (
    STATUS_DONE,
    STATUS_RUNNING,
    TYPE_VALIDATE,
    JobStore,
)

DEMO_URL = os.environ.get("ARLES_DEMO_VALIDATE_URL", "https://example.com/gallery/").rstrip(
    "/"
) + "/"
STATE_PATH = Path(os.environ.get("ARLES_DEMO_STATE", "/tmp/arles-pr-demo-state.json"))
JOBS_ROOT = Path(os.environ.get("JOBS_ROOT", "/app/data/jobs"))
PREVIEW_JOB_ID = (os.environ.get("ARLES_DEMO_PREVIEW_ID") or "").strip()
MINI_TITLE = "2/8/2012 - mini fixture"


def _demo_report() -> dict[str, Any]:
    return {
        "root_url": DEMO_URL,
        "identical": False,
        "summary": {
            "matched": 2,
            "only_remote": 1,
            "only_photos": 1,
            "content_mismatches": 1,
        },
        "warnings": ["Demo collision warning for title Demo Day 1 #2"],
        "matched": [
            {
                "title_id": "demo-day-1",
                "title": "Demo Day 1",
                "remote_url": f"{DEMO_URL}day1/",
                "photos_album_id": "demo-photos-day1",
                "photos_product_url": "https://photos.google.com/lr/album/demo-photos-day1",
                "identical": False,
                "only_remote_items": ["20120802_01"],
                "only_photos_items": ["20120802_99"],
                "mismatches": [
                    {
                        "item_id": "20120802_02",
                        "field": "caption",
                        "remote": "Demo remote caption",
                        "photos": "Demo Photos caption",
                    },
                    {
                        "item_id": "20120802_03",
                        "field": "size",
                        "remote": 2048,
                        "photos": 4096,
                    },
                ],
            },
            {
                "title_id": "demo-day-2",
                "title": "Demo Day 2",
                "remote_url": f"{DEMO_URL}day2/",
                "photos_album_id": "demo-photos-day2",
                "photos_product_url": "https://photos.google.com/lr/album/demo-photos-day2",
                "identical": True,
            },
        ],
        "only_remote": [
            {
                "title_id": "demo-orphan-remote",
                "title": "Demo orphan remote",
                "item_count": 4,
                "url": f"{DEMO_URL}orphan/",
            }
        ],
        "only_photos": [
            {
                "title_id": "demo-orphan-photos",
                "title": "Demo orphan Photos",
                "item_count": 2,
                "album_id": "demo-photos-orphan",
                "product_url": "https://photos.google.com/lr/album/demo-photos-orphan",
            }
        ],
    }


def _find_existing(store: JobStore) -> str | None:
    for job in store.list(include_archived=True):
        if job.type != TYPE_VALIDATE:
            continue
        if (job.scrape_url or "").rstrip("/") == DEMO_URL.rstrip("/"):
            return job.id
    return None


def _append_events(
    store: JobStore,
    job_id: str,
    lines: list[tuple[str, str, int, int, str]],
) -> None:
    now = datetime.now(timezone.utc)
    for stage, message, current, total, kind in lines:
        store.append_event(
            job_id,
            JobEvent(
                job_id=job_id,
                stage=stage,
                message=message,
                current=current,
                total=total,
                kind=kind,
                audience=AUDIENCE_UI,
                occurred_at=now,
            ),
        )


def _append_validate_events(store: JobStore, job_id: str) -> None:
    _append_events(
        store,
        job_id,
        [
            ("validate", "Starting validation", 0, 12, KIND_LOG),
            ("discover", "Discovering remote albums", 3, 12, KIND_PROGRESS),
            ("discover", "Indexed remote albums", 3, 12, KIND_LOG),
            ("photos", "Indexing Photos albums", 8, 12, KIND_PROGRESS),
            ("photos", "Indexed app-created Photos albums", 8, 12, KIND_LOG),
            ("compare", "Comparing albums", 12, 12, KIND_PROGRESS),
            ("compare", "Compared Demo Day 1", 12, 12, KIND_LOG),
            ("done", "Validation complete", 12, 12, KIND_LOG),
        ],
    )


def _append_preview_progress(store: JobStore, job_id: str) -> None:
    """Ensure job-detail screenshots show the sticky overall progress strip."""
    _append_events(
        store,
        job_id,
        [
            ("ingest", "Storing files", 3, 3, KIND_PROGRESS),
            ("parse", "Parsing album export", 1, 1, KIND_PROGRESS),
            ("preview_ready", MINI_TITLE, 1, 1, KIND_PROGRESS),
        ],
    )


def _find_preview_id(store: JobStore) -> str | None:
    if PREVIEW_JOB_ID:
        return PREVIEW_JOB_ID
    for job in store.list(include_archived=True):
        if job.type != "preview":
            continue
        title = (job.preview.title if job.preview is not None else "") or ""
        if title.strip() == MINI_TITLE:
            return job.id
    return None


def _open_store() -> JobStore:
    """Use the same backend selection as uvicorn (SQLAlchemy under APP_ENV=local)."""
    app = create_app()
    store = app.state.deps.store
    if not isinstance(store, JobStore):
        raise RuntimeError("create_app did not expose a JobStore")
    return store


def main() -> int:
    store = _open_store()
    existing = _find_existing(store)
    if existing:
        job_id = existing
        store.update_extra(job_id, {"validation_report": _demo_report()})
        store.set_status(job_id, STATUS_DONE, job_type=TYPE_VALIDATE)
        # Refresh progress lines so screenshots stay deterministic.
        _append_validate_events(store, job_id)
    else:
        job = store.create(
            JOBS_ROOT,
            job_type=TYPE_VALIDATE,
            folder_label="example.com",
            scrape_url=DEMO_URL,
            import_origin="web",
            extra={"validation_report": _demo_report()},
        )
        job_id = job.id
        store.set_status(job_id, STATUS_RUNNING, job_type=TYPE_VALIDATE)
        _append_validate_events(store, job_id)
        store.set_status(job_id, STATUS_DONE, job_type=TYPE_VALIDATE)
        store.update_extra(job_id, {"validation_report": _demo_report()})

    preview_id = _find_preview_id(store)
    if preview_id:
        _append_preview_progress(store, preview_id)

    payload: dict[str, Any] = {
        "validate_job_id": job_id,
        "validate_url": DEMO_URL,
        "folder_label": "example.com",
    }
    if preview_id:
        payload["preview_job_id"] = preview_id
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    prior: dict[str, Any] = {}
    if STATE_PATH.is_file():
        try:
            prior = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prior = {}
    prior.update(payload)
    STATE_PATH.write_text(json.dumps(prior, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
