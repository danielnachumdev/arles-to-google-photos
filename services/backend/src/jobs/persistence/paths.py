"""Shared id / relpath guards for persistence backends."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple


def validate_job_id(job_id: str) -> str:
    text = str(job_id)
    if not text or text in {".", ".."} or "/" in text or "\\" in text:
        raise ValueError(f"invalid job id: {job_id!r}")
    if Path(text).is_absolute():
        raise ValueError(f"invalid job id: {job_id!r}")
    return text


def validate_relpath(relpath: str) -> str:
    """Return a posix relative path. Rejects ``..`` and absolute paths."""
    normalized = str(relpath).replace("\\", "/")
    if normalized.startswith("/") or Path(normalized).is_absolute():
        raise ValueError(f"path traversal: {relpath}")
    parts = [part for part in normalized.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"path traversal: {relpath}")
    return "/".join(parts)


def parse_gcs_uri(value: str) -> Tuple[str, str]:
    """Parse ``gcs://bucket`` or ``gs://bucket/optional/prefix``."""
    text = str(value).strip()
    lowered = text.lower()
    if lowered.startswith("gcs://"):
        rest = text[6:]
    elif lowered.startswith("gs://"):
        rest = text[5:]
    else:
        raise ValueError(f"not a GCS URI: {value!r}")
    rest = rest.strip("/")
    if not rest:
        raise ValueError("GCS URI missing bucket")
    parts = rest.split("/", 1)
    bucket = parts[0].strip()
    if not bucket:
        raise ValueError("GCS URI missing bucket")
    prefix = parts[1].strip().strip("/") if len(parts) > 1 else ""
    return bucket, prefix


def normalize_gcs_bucket(value: str) -> str:
    """Bucket name only; strips ``gs://`` / ``gcs://`` if present."""
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith("gcs://") or lowered.startswith("gs://"):
        bucket, _prefix = parse_gcs_uri(text)
        return bucket
    return text.strip("/")


def normalize_gcs_prefix(value: Optional[str]) -> str:
    """Object prefix without leading/trailing slashes. Empty is allowed."""
    text = str(value or "").strip().strip("/")
    if not text:
        return ""
    parts = [
        part for part in text.replace("\\", "/").split("/") if part and part != "."
    ]
    if any(part == ".." for part in parts):
        raise ValueError(f"invalid GCS prefix: {value!r}")
    return "/".join(parts)
