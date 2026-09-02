"""FastAPI composition root: construct services, CORS, include routers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..export.editor import PreviewEditor
from ..export.parser import AlbumExportParser
from ..export.publisher import AlbumPublisher
from ..jobs.autopublish import AutoPublisher
from ..jobs.cancel import CancelService
from ..jobs.events import JobEventBus
from ..jobs.ingest import IngestService
from ..jobs.orchestrator import JobOrchestrator
from ..jobs.persistence import build_artifact_store, build_state_store
from ..jobs.publish import PublishService
from ..jobs.reprocess import ReprocessService
from ..jobs.restart import RestartService
from ..jobs.scrape import ScrapeService
from ..jobs.scraper import load_default_scraper
from ..jobs.store import JobStore
from ..jobs.tokens import AccessTokenVault
from ..jobs.workspace import JobWorkspace
from .deps import ApiDependencies
from ..version import __version__
from .routers import (
    auth_router,
    events_router,
    jobs_router,
    publish_router,
    scrape_router,
    settings_router,
    version_router,
)


def create_app(
    *,
    jobs_root: Optional[Path] = None,
    gp_factory: Optional[Callable[[str], Any]] = None,
    publisher: Optional[AlbumPublisher] = None,
    scraper: Optional[Any] = None,
    database_url: Optional[str] = None,
    artifact_bucket: Optional[str] = None,
    artifact_client: Optional[Any] = None,
    state_backend: Optional[str] = None,
) -> FastAPI:
    root = Path(jobs_root or os.environ.get("JOBS_ROOT", "data/jobs"))
    if str(state_backend or "").strip().lower() == "json":
        from ..jobs.persistence.json_state import JsonStateStore

        state = JsonStateStore(root)
    else:
        state = build_state_store(
            root,
            url=database_url,
            gcs_client=artifact_client,
            gcs_bucket=artifact_bucket,
        )
    store = JobStore.load(
        root,
        state=state,
        artifacts=build_artifact_store(
            root,
            bucket=artifact_bucket,
            client=artifact_client,
        ),
    )
    events = JobEventBus(persist=store.append_event)
    orchestrator = JobOrchestrator(store, events=events)
    orchestrator.fail_interrupted()
    cancel = CancelService(
        store=store,
        events=events,
        drop_pending=orchestrator.drop,
        on_settled=orchestrator.on_child_settled,
    )
    parser = AlbumExportParser()
    reprocess = ReprocessService(store=store, parser=parser, events=events)
    editor = PreviewEditor()
    album_publisher = publisher or AlbumPublisher()

    def _default_gp_factory(access_token: str) -> Any:
        from ..export.photos_session import google_photos_from_access_token

        return google_photos_from_access_token(access_token)

    publish = PublishService(
        store=store,
        publisher=album_publisher,
        events=events,
        gp_factory=gp_factory or _default_gp_factory,
        submit=orchestrator.submit,
    )
    auto_publisher = AutoPublisher(
        store=store,
        publish=publish,
        events=events,
        vault=AccessTokenVault(),
    )
    ingest = IngestService(
        store=store,
        parser=parser,
        events=events,
        workspace=JobWorkspace,
        auto_publisher=auto_publisher,
    )
    album_scraper = scraper if scraper is not None else load_default_scraper()
    scrape = ScrapeService(
        store=store,
        scraper=album_scraper,
        parser=parser,
        events=events,
        workspace=JobWorkspace,
        jobs_root=root,
        auto_publisher=auto_publisher,
        submit=orchestrator.submit,
    )
    restart = RestartService(
        store=store,
        scrape=scrape,
        reprocess=reprocess,
        publish=publish,
        jobs_root=root,
        submit=orchestrator.submit,
        auto_publisher=auto_publisher,
    )

    app = FastAPI(title="Arles Migrator", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.deps = ApiDependencies(
        store=store,
        ingest=ingest,
        publish=publish,
        reprocess=reprocess,
        scrape=scrape,
        restart=restart,
        cancel=cancel,
        editor=editor,
        events=events,
        jobs_root=root,
        orchestrator=orchestrator,
    )
    app.include_router(scrape_router)
    app.include_router(jobs_router)
    app.include_router(publish_router)
    app.include_router(events_router)
    app.include_router(auth_router)
    app.include_router(settings_router)
    app.include_router(version_router)
    return app


app = create_app()
