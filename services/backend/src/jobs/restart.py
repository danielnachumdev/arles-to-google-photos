"""Restart a cancelled job as a new pending run (new id), not same-id retry."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Protocol

from .store import (
    STATUS_CANCELLED,
    STATUS_DONE,
    TYPE_PREVIEW,
    TYPE_SCRAPE,
    TYPE_UPLOAD,
    Job,
    JobNotFoundError,
    JobStore,
)

RESTART_MODE_ALL = "all"
RESTART_MODE_REMAINING = "remaining"
_RESTART_MODES = frozenset({RESTART_MODE_ALL, RESTART_MODE_REMAINING})


class JobNotRestartableError(ValueError):
    """Raised when restart is requested for a job that is not cancelled."""


class _ScrapeLike(Protocol):
    def start(
        self,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        parent_job_id: Optional[str] = None,
        auto_publish: bool = False,
        access_token: Optional[str] = None,
    ) -> str:
        ...

    def finish(self, job_id: str) -> None:
        ...


class _ReprocessLike(Protocol):
    def reprocess(self, job_id: str) -> str:
        ...


class _PublishLike(Protocol):
    def start(
        self,
        source_id: str,
        *,
        access_token: str,
        parent_job_id: Optional[str] = None,
    ) -> str:
        ...

    def finish(self, upload_id: str, *, access_token: str) -> str:
        ...


class _AutoPublisherLike(Protocol):
    def remember(self, job_id: str, token: str) -> None:
        ...

    def after_preview(
        self,
        preview_id: str,
        *,
        parent_id: str,
        token_key: str,
    ) -> Optional[str]:
        ...


class RestartService:
    """Create a new job from a cancelled run and enqueue it under the orchestrator."""

    def __init__(
        self,
        store: JobStore,
        scrape: _ScrapeLike,
        reprocess: _ReprocessLike,
        publish: _PublishLike,
        jobs_root: Path,
        submit: Callable[[str, Callable[[], None]], None],
        auto_publisher: Optional[_AutoPublisherLike] = None,
    ) -> None:
        self._store = store
        self._scrape = scrape
        self._reprocess = reprocess
        self._publish = publish
        self._jobs_root = Path(jobs_root)
        self._submit = submit
        self._auto_publisher = auto_publisher

    def preview(self, job_id: str) -> Dict[str, Any]:
        try:
            source = self._store.get(job_id)
        except JobNotFoundError:
            raise
        if source.status != STATUS_CANCELLED:
            raise JobNotRestartableError("job is not cancelled")
        return self._store.restart_preview_dict(job_id)

    def restart(
        self,
        job_id: str,
        *,
        access_token: Optional[str] = None,
        mode: str = RESTART_MODE_ALL,
    ) -> str:
        try:
            source = self._store.get(job_id)
        except JobNotFoundError:
            raise
        if source.status != STATUS_CANCELLED:
            raise JobNotRestartableError("job is not cancelled")
        resolved_mode = (mode or RESTART_MODE_ALL).strip().lower() or RESTART_MODE_ALL
        if resolved_mode not in _RESTART_MODES:
            raise ValueError("unsupported restart mode")
        token = (access_token or "").strip() or None
        if source.type == TYPE_SCRAPE:
            return self._restart_scrape(source, token, mode=resolved_mode)
        if source.type == TYPE_PREVIEW:
            return self._restart_preview(source, token)
        if source.type == TYPE_UPLOAD:
            return self._restart_upload(source, token)
        raise ValueError(f"unsupported job type: {source.type}")

    def _restart_scrape(
        self,
        source: Job,
        token: Optional[str],
        *,
        mode: str,
    ) -> str:
        if not source.scrape_url:
            raise ValueError("scrape url missing")
        scrape_children = [
            child
            for child in self._store.list_children(source.id)
            if child.type == TYPE_SCRAPE
        ]
        remaining = [
            child for child in scrape_children if child.status != STATUS_DONE
        ]
        if mode == RESTART_MODE_REMAINING and scrape_children and not remaining:
            raise ValueError("no remaining scrape children to run")
        skip_urls = [
            str(child.scrape_url)
            for child in scrape_children
            if mode == RESTART_MODE_REMAINING
            and child.status == STATUS_DONE
            and child.scrape_url
        ]
        new_id = self._scrape.start(
            source.scrape_url,
            headers=source.scrape_headers,
            auto_publish=bool(source.auto_publish),
            access_token=token,
        )
        extra: Dict[str, Any] = {"restarted_from": source.id}
        if skip_urls:
            extra["skip_done_urls"] = skip_urls
        self._store.update_extra(new_id, extra)

        def run() -> None:
            self._scrape.finish(new_id)

        self._submit(new_id, run)
        return new_id

    def _restart_preview(self, source: Job, token: Optional[str]) -> str:
        created = self._store.create(
            self._jobs_root,
            job_type=TYPE_PREVIEW,
            folder_label=source.folder_label,
            auto_publish=bool(source.auto_publish),
            import_origin=source.import_origin,
        )
        self._store.copy_artifacts(source.id, created.id)
        if token and source.auto_publish and self._auto_publisher is not None:
            self._auto_publisher.remember(created.id, token)
        new_id = created.id
        auto_publish = bool(source.auto_publish)
        auto_publisher = self._auto_publisher

        def run() -> None:
            self._reprocess.reprocess(new_id)
            if auto_publish and auto_publisher is not None:
                auto_publisher.after_preview(
                    new_id, parent_id=new_id, token_key=new_id
                )

        self._submit(new_id, run)
        return new_id

    def _restart_upload(self, source: Job, token: Optional[str]) -> str:
        if not token:
            raise ValueError("google access token required")
        source_id = source.id
        if source.preview is None and source.source_job_id:
            source_id = source.source_job_id
        new_id = self._publish.start(source_id, access_token=token)

        def run() -> None:
            self._publish.finish(new_id, access_token=token)

        self._submit(new_id, run)
        return new_id
