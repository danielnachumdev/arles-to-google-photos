"""Local-filesystem ArtifactStore: ``{JOBS_ROOT}/{job_id}/`` album tree."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable, List, Optional

from ..workspace import JobWorkspace
from .artifacts import STATE_FILE_NAMES, ArtifactStore, FileTuple
from .paths import validate_job_id


class FsArtifactStore(ArtifactStore):
    """Album files on the same volume as ``JOBS_ROOT``."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def ensure_job(self, job_id: str, *, owner_id: Optional[str] = None) -> None:
        self.local_root(job_id, owner_id=owner_id).mkdir(parents=True, exist_ok=True)

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
        root = self.local_root(job_id, owner_id=owner_id)
        return JobWorkspace(root).materialize(files)

    def delete_job(self, job_id: str, *, owner_id: Optional[str] = None) -> None:
        root = self.local_root(job_id, owner_id=owner_id).resolve()
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
        del owner_id, hydrate  # local FS; owner scoping is remote-only
        return self._base_dir / validate_job_id(job_id)

    def exists(
        self, job_id: str, relpath: str, *, owner_id: Optional[str] = None
    ) -> bool:
        root = self.local_root(job_id, owner_id=owner_id)
        try:
            dest = JobWorkspace(root)._resolve_inside_root(relpath)
        except ValueError:
            return False
        return dest.is_file()

    def list(self, job_id: str, *, owner_id: Optional[str] = None) -> List[str]:
        root = self.local_root(job_id, owner_id=owner_id)
        if not root.is_dir():
            return []
        rels: List[str] = []
        for path in root.rglob("*"):
            if not path.is_file() or path.name in STATE_FILE_NAMES:
                continue
            rels.append(path.relative_to(root).as_posix())
        return rels
