"""HTTP client for Arles gallery scraping (stdlib urllib, extra headers)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; ArlesMigrator/0.1)"
DEFAULT_ACCEPT = "*/*"
DEFAULT_STREAM_CHUNK = 1024 * 1024


class FetchError(Exception):
    """Network/transport failure (not an HTTP 4xx/5xx body)."""


@dataclass(frozen=True)
class FetchedResource:
    url: str
    status_code: int
    headers: Mapping[str, str]
    content: bytes


class HttpClient(Protocol):
    def get(self, url: str, headers: Mapping[str, str]) -> FetchedResource:
        """GET ``url``. HTTP errors are returned as status_code, not raised."""

    def head(self, url: str, headers: Mapping[str, str]) -> FetchedResource:
        """HEAD ``url``. HTTP errors are returned as status_code, not raised."""

    def stream_get_to_path(
        self,
        url: str,
        headers: Mapping[str, str],
        dest: Path,
        *,
        chunk_size: int = DEFAULT_STREAM_CHUNK,
    ) -> FetchedResource:
        """GET ``url`` and write the body to ``dest`` in chunks (empty ``content``)."""


def merge_headers(extra: Mapping[str, str]) -> Dict[str, str]:
    """Default UA/Accept, then extra headers (extra wins, including UA)."""
    merged: Dict[str, str] = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": DEFAULT_ACCEPT,
    }
    extra_by_lower = {key.lower(): (key, value) for key, value in extra.items()}
    if "user-agent" in extra_by_lower:
        merged.pop("User-Agent", None)
    if "accept" in extra_by_lower:
        merged.pop("Accept", None)
    merged.update(dict(extra))
    return merged


def content_length_from_headers(headers: Mapping[str, str]) -> Optional[int]:
    raw = headers.get("content-length") or headers.get("Content-Length")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


class UrllibHttpClient:
    """stdlib urllib client. Applies ``merge_headers`` on every request."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def get(self, url: str, headers: Mapping[str, str]) -> FetchedResource:
        return self._request(url, headers, method="GET", read_body=True)

    def head(self, url: str, headers: Mapping[str, str]) -> FetchedResource:
        return self._request(url, headers, method="HEAD", read_body=False)

    def stream_get_to_path(
        self,
        url: str,
        headers: Mapping[str, str],
        dest: Path,
        *,
        chunk_size: int = DEFAULT_STREAM_CHUNK,
    ) -> FetchedResource:
        request = Request(url, headers=merge_headers(headers), method="GET")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with urlopen(request, timeout=self._timeout) as response:
                status = int(getattr(response, "status", 200))
                final_url = str(response.geturl() or url)
                raw_headers = {
                    str(key).lower(): str(value)
                    for key, value in response.headers.items()
                }
                if status != 200:
                    # Drain lightly; caller treats non-200 like a failed candidate.
                    response.read()
                    return FetchedResource(
                        url=final_url,
                        status_code=status,
                        headers=raw_headers,
                        content=b"",
                    )
                written = 0
                with tmp.open("wb") as handle:
                    while True:
                        chunk = response.read(max(int(chunk_size), 64 * 1024))
                        if not chunk:
                            break
                        handle.write(chunk)
                        written += len(chunk)
                tmp.replace(dest)
                if "content-length" not in raw_headers:
                    raw_headers = dict(raw_headers)
                    raw_headers["content-length"] = str(written)
                return FetchedResource(
                    url=final_url,
                    status_code=status,
                    headers=raw_headers,
                    content=b"",
                )
        except HTTPError as exc:
            raw_headers = {
                str(key).lower(): str(value)
                for key, value in (exc.headers or {}).items()
            }
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            return FetchedResource(
                url=url,
                status_code=int(exc.code),
                headers=raw_headers,
                content=b"",
            )
        except URLError as exc:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise FetchError(f"Failed to fetch {url}: {exc.reason}") from exc
        except Exception:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise

    def _request(
        self,
        url: str,
        headers: Mapping[str, str],
        *,
        method: str,
        read_body: bool,
    ) -> FetchedResource:
        request = Request(url, headers=merge_headers(headers), method=method)
        try:
            with urlopen(request, timeout=self._timeout) as response:
                content = response.read() if read_body else b""
                status = int(getattr(response, "status", 200))
                final_url = str(response.geturl() or url)
                raw_headers = {
                    str(key).lower(): str(value)
                    for key, value in response.headers.items()
                }
                return FetchedResource(
                    url=final_url,
                    status_code=status,
                    headers=raw_headers,
                    content=content,
                )
        except HTTPError as exc:
            body = b""
            if read_body and exc.fp is not None:
                body = exc.read()
            raw_headers = {
                str(key).lower(): str(value)
                for key, value in (exc.headers or {}).items()
            }
            return FetchedResource(
                url=url,
                status_code=int(exc.code),
                headers=raw_headers,
                content=body,
            )
        except URLError as exc:
            raise FetchError(f"Failed to fetch {url}: {exc.reason}") from exc
