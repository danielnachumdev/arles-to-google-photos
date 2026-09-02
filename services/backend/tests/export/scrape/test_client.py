"""TDD: scrape HTTP client applies extra headers on every request."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Dict, List, Tuple
from urllib.error import URLError

import pytest

from src.export.scrape.client import (
    DEFAULT_USER_AGENT,
    FetchError,
    UrllibHttpClient,
    merge_headers,
)


class _HeaderProbeHandler(BaseHTTPRequestHandler):
    seen: List[Tuple[str, Dict[str, str]]] = []
    cookie_ok = "session=abc"
    auth_ok = "Bearer secret-token"

    def do_GET(self) -> None:
        headers = {key.lower(): value for key, value in self.headers.items()}
        _HeaderProbeHandler.seen.append((self.path, headers))
        cookie = headers.get("cookie", "")
        auth = headers.get("authorization", "")
        if cookie != self.cookie_ok or auth != self.auth_ok:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"forbidden")
            return
        if self.path == "/missing.jpg":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"nope")
            return
        body = b"<html><body>ok</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args: object) -> None:
        return


class TestUrllibHttpClient:
    """Live loopback server + UrllibHttpClient (setup/teardown per test)."""

    def setup_method(self) -> None:
        _HeaderProbeHandler.seen = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _HeaderProbeHandler)
        thread = Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        host, port = self.server.server_address[:2]
        self.base = f"http://{host}:{port}"
        self.http = UrllibHttpClient(timeout=5.0)
        self.auth_headers = {
            "Cookie": "session=abc",
            "Authorization": "Bearer secret-token",
        }

    def teardown_method(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def test_sends_cookie_and_authorization(self) -> None:
        result = self.http.get(f"{self.base}/Day1/index.html", self.auth_headers)

        assert result.status_code == 200
        assert result.content == b"<html><body>ok</body></html>"
        assert _HeaderProbeHandler.seen
        sent = _HeaderProbeHandler.seen[0][1]
        assert sent["cookie"] == "session=abc"
        assert sent["authorization"] == "Bearer secret-token"
        assert sent["user-agent"] == DEFAULT_USER_AGENT

    def test_custom_user_agent_overrides_default(self) -> None:
        extra = {**self.auth_headers, "User-Agent": "ArlesAlbumBot/9"}
        result = self.http.get(f"{self.base}/album", extra)

        assert result.status_code == 200
        sent = _HeaderProbeHandler.seen[0][1]
        assert sent["user-agent"] == "ArlesAlbumBot/9"

    def test_returns_404_without_raising(self) -> None:
        result = self.http.get(f"{self.base}/missing.jpg", self.auth_headers)

        assert result.status_code == 404
        assert result.content == b"nope"


class TestHttpClientHelpers:
    def test_merge_headers_extra_accept_replaces_default(self) -> None:
        merged = merge_headers({"Accept": "text/html"})
        assert merged["Accept"] == "text/html"
        assert merged["User-Agent"] == DEFAULT_USER_AGENT

    def test_urlerror_becomes_fetch_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_args: object, **_kwargs: object) -> None:
            raise URLError("down")

        monkeypatch.setattr("src.export.scrape.client.urlopen", boom)
        with pytest.raises(FetchError, match="Failed to fetch"):
            UrllibHttpClient(timeout=1).get("http://127.0.0.1/x", {})
