"""Mirror local ``migrator.sqlite`` to GCS when ``APP_ENV`` is cloud.

SQLite cannot open ``gs://`` URLs. When ``DATABASE_URL`` is unset this module
copies ``{JOBS_ROOT}/migrator.sqlite`` to ``{GCS_PREFIX}/migrator.sqlite``
(or ``migrator.sqlite`` when the prefix is empty) so Cloud Run recreates can
hydrate job metadata. ``GCS_BUCKET`` is the bucket address, not the detector.

Uploads are **scheduled** onto a daemon thread and rate-limited to at most
once per second so cancel/archive/API writes do not block on GCS. ``flush`` /
``close`` still upload immediately. Last-writer-wins. Safe only with **one**
Cloud Run instance and **one** uvicorn worker. Do not use GCS FUSE. Prefer
``DATABASE_URL`` (Cloud SQL) when scaling out.
"""
from __future__ import annotations

import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

from .paths import normalize_gcs_bucket, normalize_gcs_prefix
from .sqlalchemy_state import DB_NAME

SQLITE_GCS_NAME = DB_NAME
DEFAULT_UPLOAD_INTERVAL_S = 1.0


def sqlite_gcs_object_key(prefix: str = "") -> str:
    """Object key: ``{prefix}/migrator.sqlite`` or ``migrator.sqlite``."""
    normalized = normalize_gcs_prefix(prefix)
    if normalized:
        return f"{normalized}/{SQLITE_GCS_NAME}"
    return SQLITE_GCS_NAME


class GcsSqliteMirror:
    """Download/upload ``{JOBS_ROOT}/migrator.sqlite`` to a single GCS object."""

    def __init__(
        self,
        local_path: Path,
        *,
        bucket: str,
        prefix: str = "jobs",
        client: Optional[Any] = None,
        interval_s: float = DEFAULT_UPLOAD_INTERVAL_S,
    ) -> None:
        bucket_name = normalize_gcs_bucket(bucket)
        if not bucket_name:
            raise ValueError("GCS_BUCKET is required")
        self._local_path = Path(local_path)
        self._bucket_name = bucket_name
        self._prefix = normalize_gcs_prefix(prefix)
        self._client_obj = client
        self._bucket_obj: Any = None
        self._interval_s = max(0.0, float(interval_s))
        self._lock = threading.Lock()
        self._dirty = False
        self._wakeup = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    @property
    def prefix(self) -> str:
        return self._prefix

    @property
    def object_key(self) -> str:
        return sqlite_gcs_object_key(self._prefix)

    @property
    def local_path(self) -> Path:
        return self._local_path

    @property
    def interval_s(self) -> float:
        return self._interval_s

    @property
    def _client(self) -> Any:
        if self._client_obj is None:
            from google.cloud import storage  # type: ignore[import-untyped]

            self._client_obj = storage.Client()
        return self._client_obj

    @property
    def _bucket(self) -> Any:
        if self._bucket_obj is None:
            self._bucket_obj = self._client.bucket(self._bucket_name)
        return self._bucket_obj

    def _blob(self) -> Any:
        return self._bucket.blob(self.object_key)

    def hydrate(self) -> bool:
        """Copy the GCS object onto ``local_path`` if it exists. Returns True if downloaded."""
        blob = self._blob()
        if not blob.exists():
            return False
        self._local_path.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(self._local_path))
        return True

    def upload(self) -> None:
        """Replace the GCS object with a snapshot of the local sqlite file (no-op if missing)."""
        if not self._local_path.is_file():
            return
        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="migrator-sqlite-",
                suffix=".sqlite",
                delete=False,
            ) as handle:
                tmp_path = Path(handle.name)
            shutil.copy2(self._local_path, tmp_path)
            self._blob().upload_from_filename(str(tmp_path))
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    def schedule(self) -> None:
        """Mark dirty and wake the background uploader (non-blocking)."""
        with self._lock:
            self._dirty = True
            self._ensure_thread_unlocked()
        self._wakeup.set()

    def flush(self) -> None:
        """Upload immediately if the local file exists. Clears the dirty flag."""
        with self._lock:
            self._dirty = False
        self.upload()

    def close(self) -> None:
        """Stop the background thread and flush any pending upload."""
        self._stop.set()
        self._wakeup.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=8.0)
        self.flush()

    def _ensure_thread_unlocked(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="gcs-sqlite-mirror",
            daemon=True,
        )
        self._thread.start()

    def _consume_dirty(self) -> bool:
        with self._lock:
            dirty = self._dirty
            self._dirty = False
            return dirty

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wakeup.wait()
            if self._stop.is_set():
                break
            self._wakeup.clear()
            if not self._consume_dirty():
                continue
            try:
                self.upload()
            except Exception:
                with self._lock:
                    self._dirty = True
                continue
            if self._interval_s > 0:
                self._stop.wait(self._interval_s)
