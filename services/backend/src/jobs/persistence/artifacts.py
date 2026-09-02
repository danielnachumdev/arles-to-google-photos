"""ArtifactStore: durable *files* (uploaded Arles tree), not job metadata."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

FileTuple = Tuple[str, bytes, Optional[float]]

# Omitted from ``list`` (and not uploaded by GCS). Json StateStore may still
# write these next to the local cache; they are not album artifacts.
STATE_FILE_NAMES = frozenset(
    {
        "job.json",
        "events.json",
        "job.json.tmp",
        "events.json.tmp",
    }
)


class ArtifactStore(ABC):
    """Durable album files. Implementations take ``base_dir: Path`` (JOBS_ROOT).

    ``local_root`` returns a local directory the parser / publisher can use.
    Filesystem backends use ``{JOBS_ROOT}/{job_id}/`` directly. The GCS
    backend hydrates/caches objects there (``JOBS_ROOT`` is not the bucket).

    Optional ``owner_id`` scopes remote object keys (GCS) under
    ``{prefix}/users/{owner_id}/{job_id}/`` so tenants do not share prefixes.
    Local cache dirs stay ``{JOBS_ROOT}/{job_id}/`` (job ids are globally unique).
    """

    @abstractmethod
    def ensure_job(self, job_id: str, *, owner_id: Optional[str] = None) -> None:
        """Create the job's artifact namespace if missing."""

    @abstractmethod
    def put(
        self,
        job_id: str,
        relpath: str,
        data: bytes,
        last_modified_ts: Optional[float] = None,
        *,
        owner_id: Optional[str] = None,
    ) -> None:
        """Write one relative path. Rejects ``..`` / absolute paths."""

    @abstractmethod
    def materialize(
        self,
        job_id: str,
        files: Iterable[FileTuple],
        *,
        owner_id: Optional[str] = None,
    ) -> Path:
        """Write many files. Returns the local filesystem root for this job."""

    @abstractmethod
    def delete_job(self, job_id: str, *, owner_id: Optional[str] = None) -> None:
        """Remove all artifacts for a job."""

    @abstractmethod
    def local_root(
        self,
        job_id: str,
        *,
        owner_id: Optional[str] = None,
        hydrate: bool = True,
    ) -> Path:
        """Local directory for this job.

        When ``hydrate`` is True (default), remote backends fill the cache from
        object storage. Pass ``hydrate=False`` for cheap path resolution (e.g.
        JobStore boot) so Cloud Run does not download every album before bind.
        """

    @abstractmethod
    def exists(
        self, job_id: str, relpath: str, *, owner_id: Optional[str] = None
    ) -> bool:
        """True if the relative artifact exists."""

    @abstractmethod
    def list(self, job_id: str, *, owner_id: Optional[str] = None) -> List[str]:
        """Relative artifact paths (forward slashes). Omits state json files."""
