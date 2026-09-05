"""GCS ArtifactStore: album trees in a bucket; sparse local scratch on JOBS_ROOT.

Album **files** only. ``STATE_FILE_NAMES`` are intentionally not uploaded.
Job metadata lives in SQLAlchemy. When ``APP_ENV`` is cloud and ``DATABASE_URL``
is blank, ``migrator.sqlite`` is mirrored separately (see ``gcs_sqlite.py``).

Cloud Run's container filesystem counts toward the memory limit, so this store:

1. Uploads each object to GCS one at a time.
2. Keeps only **structure** HTML/CSS in the local scratch after put.
3. On ``local_root(hydrate=True)``, downloads structure files and creates empty
   media placeholders + ``arles-media-index.json`` (sizes/mtimes from GCS).
4. ``ensure_file`` downloads one media body on demand (preview / publish).

Object keys: ``{prefix}/users/{owner_id}/{job_id}/…`` when ``owner_id`` is set;
otherwise ``{prefix}/{job_id}/…`` (legacy / unowned).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ...export.media_index import MediaIndex, MediaIndexEntry, clear_media_index_cache
from ..workspace import JobWorkspace
from .album_paths import AlbumArtifactClassifier
from .artifacts import STATE_FILE_NAMES, ArtifactStore, FileTuple
from .paths import (
    normalize_gcs_bucket,
    normalize_gcs_prefix,
    validate_job_id,
    validate_relpath,
)
from .sparse_cache import SparseAlbumWorkspace

_MTIME_META_KEY = "arles_mtime"
_SIZE_META_KEY = "arles_size"


class GcsArtifactStore(ArtifactStore):
    """Album files in Google Cloud Storage; sparse hydrate to ``JOBS_ROOT``."""

    def __init__(
        self,
        base_dir: Path,
        *,
        bucket: str,
        prefix: str = "jobs",
        client: Optional[Any] = None,
        classifier: Optional[AlbumArtifactClassifier] = None,
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
        self._classifier = classifier or AlbumArtifactClassifier()

    @property
    def retains_full_local_tree(self) -> bool:
        return False

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

    def put_file(
        self,
        job_id: str,
        relpath: str,
        path: Path,
        last_modified_ts: Optional[float] = None,
        *,
        owner_id: Optional[str] = None,
    ) -> None:
        """Upload from a local path without holding other album files in RAM."""
        safe_rel = validate_relpath(relpath)
        root = self._cache_root(job_id)
        sparse = SparseAlbumWorkspace(root, classifier=self._classifier)
        source = Path(path)
        size = int(source.stat().st_size)
        if Path(safe_rel).name in STATE_FILE_NAMES:
            dest = JobWorkspace(root)._resolve_inside_root(safe_rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            return
        blob = self._blob(job_id, safe_rel, owner_id=owner_id)
        meta: Dict[str, str] = {_SIZE_META_KEY: str(size)}
        if last_modified_ts is not None:
            meta[_MTIME_META_KEY] = f"{float(last_modified_ts):.6f}"
        blob.metadata = meta
        blob.upload_from_filename(str(source))
        if self._classifier.is_media(safe_rel):
            index = MediaIndex.read(root)
            index.put(
                safe_rel,
                MediaIndexEntry(size_bytes=size, mtime=last_modified_ts),
            )
            sparse.place_media_placeholder(
                safe_rel, size_bytes=size, mtime=last_modified_ts
            )
            sparse.write_media_index(index)
            clear_media_index_cache()
            return
        dest = JobWorkspace(root)._resolve_inside_root(safe_rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        if last_modified_ts is not None:
            os.utime(dest, (last_modified_ts, last_modified_ts))

    def materialize(
        self,
        job_id: str,
        files: Iterable[FileTuple],
        *,
        owner_id: Optional[str] = None,
    ) -> Path:
        root = self._cache_root(job_id)
        workspace = JobWorkspace(root)
        sparse = SparseAlbumWorkspace(root, classifier=self._classifier)
        index = MediaIndex()
        for rel, data, ts in files:
            safe_rel = validate_relpath(rel)
            if Path(safe_rel).name in STATE_FILE_NAMES:
                workspace.materialize([(safe_rel, data, ts)])
                continue
            workspace.materialize([(safe_rel, data, ts)])
            blob = self._blob(job_id, safe_rel, owner_id=owner_id)
            meta: Dict[str, str] = {_SIZE_META_KEY: str(len(data))}
            if ts is not None:
                meta[_MTIME_META_KEY] = f"{float(ts):.6f}"
            blob.metadata = meta
            blob.upload_from_string(data)
            if self._classifier.is_media(safe_rel):
                index.put(
                    safe_rel,
                    MediaIndexEntry(size_bytes=len(data), mtime=ts),
                )
                sparse.place_media_placeholder(
                    safe_rel, size_bytes=len(data), mtime=ts
                )
        if index.to_dict():
            sparse.write_media_index(index)
            clear_media_index_cache()
        return root

    def ensure_file(
        self,
        job_id: str,
        relpath: str,
        *,
        owner_id: Optional[str] = None,
    ) -> Path:
        safe_rel = validate_relpath(relpath)
        root = self._cache_root(job_id)
        dest = JobWorkspace(root)._resolve_inside_root(safe_rel)
        if dest.is_file() and dest.stat().st_size > 0:
            return dest
        if Path(safe_rel).name in STATE_FILE_NAMES:
            if dest.is_file():
                return dest
            raise FileNotFoundError(safe_rel)
        blob = self._blob(job_id, safe_rel, owner_id=owner_id)
        if not blob.exists():
            raise FileNotFoundError(safe_rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(dest))
        mtime = self._blob_mtime(blob)
        if mtime is not None:
            os.utime(dest, (mtime, mtime))
        return dest

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
        clear_media_index_cache()

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
            self._hydrate_sparse(job_id, root, rels, owner_id=owner_id)
        return root

    def _hydrate_sparse(
        self,
        job_id: str,
        root: Path,
        rels: List[str],
        *,
        owner_id: Optional[str] = None,
    ) -> None:
        sparse = SparseAlbumWorkspace(root, classifier=self._classifier)
        index = MediaIndex()
        for rel in rels:
            dest = root / rel
            if self._classifier.is_structure(rel):
                if dest.is_file() and dest.stat().st_size > 0:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                self._blob(job_id, rel, owner_id=owner_id).download_to_filename(
                    str(dest)
                )
                continue
            blob = self._blob(job_id, rel, owner_id=owner_id)
            size = self._blob_size(blob)
            mtime = self._blob_mtime(blob)
            index.put(rel, MediaIndexEntry(size_bytes=size, mtime=mtime))
            if not dest.is_file():
                sparse.place_media_placeholder(rel, size_bytes=size, mtime=mtime)
        sparse.write_media_index(index)
        clear_media_index_cache()

    def _blob_size(self, blob: Any) -> int:
        meta = getattr(blob, "metadata", None) or {}
        if isinstance(meta, dict) and _SIZE_META_KEY in meta:
            try:
                return int(meta[_SIZE_META_KEY])
            except (TypeError, ValueError):
                pass
        size = getattr(blob, "size", None)
        if size is not None:
            try:
                return int(size)
            except (TypeError, ValueError):
                pass
        return 0

    def _blob_mtime(self, blob: Any) -> Optional[float]:
        meta = getattr(blob, "metadata", None) or {}
        if isinstance(meta, dict) and _MTIME_META_KEY in meta:
            try:
                return float(meta[_MTIME_META_KEY])
            except (TypeError, ValueError):
                return None
        return None

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
