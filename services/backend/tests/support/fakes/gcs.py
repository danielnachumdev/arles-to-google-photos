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
        meta_store: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> None:
        self._store = store
        self.name = name
        self._client = client
        self._meta_store = meta_store if meta_store is not None else {}

    @property
    def metadata(self) -> Dict[str, str]:
        return dict(self._meta_store.get(self.name, {}))

    @metadata.setter
    def metadata(self, value: Optional[Dict[str, str]]) -> None:
        if not value:
            self._meta_store.pop(self.name, None)
        else:
            self._meta_store[self.name] = dict(value)

    @property
    def size(self) -> int:
        data = self._store.get(self.name)
        return 0 if data is None else len(data)

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
        self._meta_store.pop(self.name, None)


class FakeBucket:
    """In-memory bucket: ``blob`` / ``list_blobs`` / ``copy_blob``."""

    def __init__(
        self,
        blobs: Dict[str, bytes],
        name: str,
        client: Optional["FakeGcsClient"] = None,
        meta: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> None:
        self.name = name
        self._blobs = blobs
        self._client = client
        self._meta = meta if meta is not None else {}

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self._blobs, name, client=self._client, meta_store=self._meta)

    def list_blobs(self, prefix: str = "", **_kwargs: object) -> Iterator[FakeBlob]:
        for name in list(self._blobs):
            if name.startswith(prefix):
                yield FakeBlob(
                    self._blobs, name, client=self._client, meta_store=self._meta
                )

    def copy_blob(
        self,
        blob: FakeBlob,
        _destination_bucket: Optional["FakeBucket"] = None,
        new_name: str = "",
        **_kwargs: object,
    ) -> FakeBlob:
        dest = new_name or blob.name
        self._blobs[dest] = self._blobs[blob.name]
        if blob.name in self._meta:
            self._meta[dest] = dict(self._meta[blob.name])
        return FakeBlob(self._blobs, dest, client=self._client, meta_store=self._meta)


class FakeGcsClient:
    """Application-Default-Credentials-free client for unit tests."""

    def __init__(self) -> None:
        self._buckets: Dict[str, Dict[str, bytes]] = {}
        self._meta: Dict[str, Dict[str, Dict[str, str]]] = {}
        self.upload_from_filename_calls = 0
        self.download_to_filename_calls = 0

    def bucket(self, name: str) -> FakeBucket:
        self._buckets.setdefault(name, {})
        self._meta.setdefault(name, {})
        return FakeBucket(
            self._buckets[name], name, client=self, meta=self._meta[name]
        )

    def list_blobs(
        self, bucket_or_name: object, prefix: str = "", **_kwargs: object
    ) -> Iterator[FakeBlob]:
        if isinstance(bucket_or_name, str):
            name = bucket_or_name
        else:
            name = str(getattr(bucket_or_name, "name", ""))
        return self.bucket(name).list_blobs(prefix=prefix)
