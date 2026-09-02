"""HttpClient strategy double + deterministic clock for scrape ETA tests."""
from __future__ import annotations

from typing import Dict, List, Mapping, Tuple

from src.export.scrape.client import FetchedResource


class FakeClock:
    """Monotonic clock the test can advance (seconds)."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeHttpClient:
    """In-memory HttpClient: url → (status, body), optional per-url delay."""

    def __init__(
        self,
        pages: Mapping[str, Tuple[int, bytes]],
        *,
        clock: FakeClock | None = None,
        delays: Mapping[str, float] | None = None,
        default_delay: float = 0.0,
    ) -> None:
        self.pages = dict(pages)
        self.calls: List[Tuple[str, Dict[str, str]]] = []
        self.clock = clock
        self.delays = dict(delays or {})
        self.default_delay = default_delay

    def get(self, url: str, headers: Mapping[str, str]) -> FetchedResource:
        self.calls.append((url, dict(headers)))
        delay = self.delays.get(url, self.default_delay)
        if delay and self.clock is not None:
            self.clock.advance(delay)
        if url not in self.pages:
            return FetchedResource(
                url=url,
                status_code=404,
                headers={},
                content=b"",
            )
        status, content = self.pages[url]
        return FetchedResource(
            url=url,
            status_code=status,
            headers={"content-type": "application/octet-stream"},
            content=content,
        )
