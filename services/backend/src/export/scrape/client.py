"""HTTP client for Arles gallery scraping (stdlib urllib, extra headers)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; ArlesMigrator/0.1)"
DEFAULT_ACCEPT = "*/*"


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


class UrllibHttpClient:
    """stdlib urllib client. Applies ``merge_headers`` on every request."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def get(self, url: str, headers: Mapping[str, str]) -> FetchedResource:
        request = Request(url, headers=merge_headers(headers), method="GET")
        try:
            with urlopen(request, timeout=self._timeout) as response:
                content = response.read()
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
            body = exc.read() if exc.fp is not None else b""
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
