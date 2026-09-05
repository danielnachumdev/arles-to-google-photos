"""GCS ArtifactStore: album trees in a bucket; ``JOBS_ROOT`` is a local cache.

Album **files** only. ``STATE_FILE_NAMES`` (``job.json``, ``events.json``, …)
are intentionally not uploaded. Job metadata lives in SQLAlchemy. When
``APP_ENV`` is cloud and ``DATABASE_URL`` is blank, ``migrator.sqlite`` is
mirrored separately to ``{prefix}/migrator.sqlite`` (see ``gcs_sqlite.py``).
That sqlite mirror is last-writer-wins and only safe with one instance.

Object keys: ``{prefix}/users/{owner_id}/{job_id}/…`` when ``owner_id`` is set;
otherwise ``{prefix}/{job_id}/…`` (legacy / unowned).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Iterable, List, Optional

from ..workspace import JobWorkspace
from .artifacts import STATE_FILE_NAMES, ArtifactStore, FileTuple
from .paths import (
    normalize_gcs_bucket,
    normalize_gcs_prefix,
    validate_job_id,
    validate_relpath,
)


class GcsArtifactStore(ArtifactStore):
    """Album files in Google Cloud Storage; hydrate to ``{JOBS_ROOT}/{job_id}/``.

    Auth is Application Default Credentials (Cloud Run service account,
    ``GOOGLE_APPLICATION_CREDENTIALS``, or ``gcloud auth application-default login``).
    Do not bake keys into the image or the repo.
    """

    def __init__(
        self,
        base_dir: Path,
        *,
        bucket: str,
        prefix: str = "jobs",
        client: Optional[Any] = None,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        bucket_name = normalize_gcs_bucket(bucket)
        if not bucket_name:
            raise ValueError("GCS_BUCKET is required")
        self._bucket_name = bucket_name
        self._prefix = normalize_gcs_prefix(prefix)
        self._client_obj = client
        self._bucket_obj: Any = None

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    @property
    def prefix(self) -> str:
        return self._prefix

    @property
    def _client(self) -> Any:
        if self._client_obj is None:
            from google.cloud import storage

            self._client_obj = storage.Client()
        return self._client_obj

    @property
    def _bucket(self) -> Any:
        if self._bucket_obj is None:
            self._bucket_obj = self._client.bucket(self._bucket_name)
        return self._bucket_obj

    def _cache_root(self, job_id: str) -> Path:
        return self._base_dir / validate_job_id(job_id)

    def _job_prefix(self, job_id: str, *, owner_id: Optional[str] = None) -> str:
        validated = validate_job_id(job_id)
        owner_seg = ""
        if owner_id:
            owner_seg = f"users/{validate_job_id(owner_id)}/"
        if self._prefix:
            return f"{self._prefix}/{owner_seg}{validated}/"
        return f"{owner_seg}{validated}/"

    def _object_key(
        self, job_id: str, relpath: str, *, owner_id: Optional[str] = None
    ) -> str:
        rel = validate_relpath(relpath)
        return f"{self._job_prefix(job_id, owner_id=owner_id)}{rel}"

    def _blob(
        self, job_id: str, relpath: str, *, owner_id: Optional[str] = None
    ) -> Any:
        return self._bucket.blob(
            self._object_key(job_id, relpath, owner_id=owner_id)
        )

    def ensure_job(self, job_id: str, *, owner_id: Optional[str] = None) -> None:
        self._cache_root(job_id).mkdir(parents=True, exist_ok=True)

    def put(
        self,
        job_id: str,
        relpath: str,
        data: bytes,
        last_modified_ts: Optional[float] = None,
        *,
        owner_id: Optional[str] = None,
    ) -> None:
        self.materialize(
            job_id, [(relpath, data, last_modified_ts)], owner_id=owner_id
        )

    def materialize(
        self,
        job_id: str,
        files: Iterable[FileTuple],
        *,
        owner_id: Optional[str] = None,
    ) -> Path:
        # One file at a time so large albums do not need 2× album RAM.
        root = self._cache_root(job_id)
        workspace = JobWorkspace(root)
        for rel, data, ts in files:
            safe_rel = validate_relpath(rel)
            workspace.materialize([(safe_rel, data, ts)])
            if Path(safe_rel).name in STATE_FILE_NAMES:
                continue
            self._blob(job_id, safe_rel, owner_id=owner_id).upload_from_string(data)
        return root

    def delete_job(self, job_id: str, *, owner_id: Optional[str] = None) -> None:
        prefix = self._job_prefix(job_id, owner_id=owner_id)
        for blob in list(self._bucket.list_blobs(prefix=prefix)):
            blob.delete()
        root = self._cache_root(job_id).resolve()
        base = self._base_dir.resolve()
        if root == base or not root.is_relative_to(base):
            raise ValueError("refusing to delete a path outside the artifact store")
        if root.is_dir():
            shutil.rmtree(root)

    def local_root(
        self,
        job_id: str,
        *,
        owner_id: Optional[str] = None,
        hydrate: bool = True,
    ) -> Path:
        root = self._cache_root(job_id)
        if not hydrate:
            return root
        rels = self.list(job_id, owner_id=owner_id)
        if rels:
            root.mkdir(parents=True, exist_ok=True)
            self._hydrate(job_id, root, rels, owner_id=owner_id)
        return root

    def _hydrate(
        self,
        job_id: str,
        root: Path,
        rels: List[str],
        *,
        owner_id: Optional[str] = None,
    ) -> None:
        for rel in rels:
            dest = root / rel
            if dest.is_file():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._blob(job_id, rel, owner_id=owner_id).download_to_filename(str(dest))

    def exists(
        self, job_id: str, relpath: str, *, owner_id: Optional[str] = None
    ) -> bool:
        try:
            validate_job_id(job_id)
            rel = validate_relpath(relpath)
        except ValueError:
            return False
        return bool(self._blob(job_id, rel, owner_id=owner_id).exists())

    def list(self, job_id: str, *, owner_id: Optional[str] = None) -> List[str]:
        prefix = self._job_prefix(job_id, owner_id=owner_id)
        rels: List[str] = []
        for blob in self._bucket.list_blobs(prefix=prefix):
            name = str(getattr(blob, "name", "") or "")
            if not name.startswith(prefix):
                continue
            rel = name[len(prefix):]
            if not rel or rel.endswith("/"):
                continue
            if Path(rel).name in STATE_FILE_NAMES:
                continue
            rels.append(rel)
        return rels
