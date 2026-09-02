"""In-memory GCS stand-in for ArtifactStore unit tests (no real bucket)."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterator, Optional


class FakeBlob:
    """Minimal ``google.cloud.storage.Blob`` surface used by GcsArtifactStore."""

    def __init__(
        self,
        store: Dict[str, bytes],
        name: str,
        client: Optional["FakeGcsClient"] = None,
    ) -> None:
        self._store = store
        self.name = name
        self._client = client

    def upload_from_string(self, data: object, **_kwargs: object) -> None:
        if isinstance(data, bytes):
            payload = data
        elif isinstance(data, str):
            payload = data.encode("utf-8")
        else:
            payload = bytes(data)  # type: ignore[arg-type]
        self._store[self.name] = payload

    def upload_from_filename(self, filename: str, **_kwargs: object) -> None:
        if self._client is not None:
            self._client.upload_from_filename_calls += 1
        self._store[self.name] = Path(filename).read_bytes()

    def download_to_filename(self, filename: str, **_kwargs: object) -> None:
        if self._client is not None:
            self._client.download_to_filename_calls += 1
        if self.name not in self._store:
            raise FileNotFoundError(self.name)
        dest = Path(filename)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self._store[self.name])

    def download_as_bytes(self, **_kwargs: object) -> bytes:
        if self.name not in self._store:
            raise FileNotFoundError(self.name)
        return self._store[self.name]

    def exists(self, **_kwargs: object) -> bool:
        return self.name in self._store

    def delete(self, **_kwargs: object) -> None:
        self._store.pop(self.name, None)


class FakeBucket:
    """In-memory bucket: ``blob`` / ``list_blobs`` / ``copy_blob``."""

    def __init__(
        self,
        blobs: Dict[str, bytes],
        name: str,
        client: Optional["FakeGcsClient"] = None,
    ) -> None:
        self.name = name
        self._blobs = blobs
        self._client = client

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self._blobs, name, client=self._client)

    def list_blobs(self, prefix: str = "", **_kwargs: object) -> Iterator[FakeBlob]:
        for name in list(self._blobs):
            if name.startswith(prefix):
                yield FakeBlob(self._blobs, name, client=self._client)

    def copy_blob(
        self,
        blob: FakeBlob,
        _destination_bucket: Optional["FakeBucket"] = None,
        new_name: str = "",
        **_kwargs: object,
    ) -> FakeBlob:
        dest = new_name or blob.name
        self._blobs[dest] = self._blobs[blob.name]
        return FakeBlob(self._blobs, dest, client=self._client)


class FakeGcsClient:
    """Application-Default-Credentials-free client for unit tests."""

    def __init__(self) -> None:
        self._buckets: Dict[str, Dict[str, bytes]] = {}
        self.upload_from_filename_calls = 0
        self.download_to_filename_calls = 0

    def bucket(self, name: str) -> FakeBucket:
        self._buckets.setdefault(name, {})
        return FakeBucket(self._buckets[name], name, client=self)

    def list_blobs(self, bucket_or_name: object, prefix: str = "", **_kwargs: object) -> Iterator[FakeBlob]:
        if isinstance(bucket_or_name, str):
            name = bucket_or_name
        else:
            name = str(getattr(bucket_or_name, "name", ""))
        return self.bucket(name).list_blobs(prefix=prefix)
