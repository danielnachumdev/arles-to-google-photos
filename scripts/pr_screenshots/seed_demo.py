#!/usr/bin/env python3
"""Seed a local Arles API with PII-safe demo jobs for SPA PR screenshots.

Uploads tests/fixtures/day1_mini as a preview job, then seeds a fabricated
validate report inside the backend container (JobStore) and restarts the
backend so the in-process cache reloads.

Usage:
  python3 scripts/pr_screenshots/seed_demo.py
  ARLES_API_URL=http://127.0.0.1:8000 python3 scripts/pr_screenshots/seed_demo.py

Env (all optional):
  ARLES_API_URL           default http://127.0.0.1:8000
  ARLES_COMPOSE_DIR       repo root with docker-compose.yml (default: auto)
  ARLES_DEMO_STATE        default /tmp/arles-pr-demo/state.json
  ARLES_DEMO_FIXTURE      default <repo>/services/backend/tests/fixtures/day1_mini
  ARLES_SKIP_VALIDATE     set to 1 to skip validate JobStore seed + restart
  ARLES_SKIP_RESTART      set to 1 to skip backend restart after validate seed
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

REPO_ROOT = Path(__file__).resolve().parents[2]
API = os.environ.get("ARLES_API_URL", "http://127.0.0.1:8000").rstrip("/")
STATE_PATH = Path(os.environ.get("ARLES_DEMO_STATE", "/tmp/arles-pr-demo/state.json"))
FIXTURE = Path(
    os.environ.get(
        "ARLES_DEMO_FIXTURE",
        str(REPO_ROOT / "services" / "backend" / "tests" / "fixtures" / "day1_mini"),
    )
)
COMPOSE_DIR = Path(os.environ.get("ARLES_COMPOSE_DIR", str(REPO_ROOT)))
SKIP_VALIDATE = os.environ.get("ARLES_SKIP_VALIDATE", "").strip() in {"1", "true", "yes"}
SKIP_RESTART = os.environ.get("ARLES_SKIP_RESTART", "").strip() in {"1", "true", "yes"}
MINI_TITLE = "2/8/2012 - mini fixture"


def _get(path: str) -> Any:
    with urllib.request.urlopen(f"{API}{path}", timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait_api(timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            _get("/api/settings")
            return
        except Exception as exc:  # noqa: BLE001 — retry until up
            last_err = exc
            time.sleep(0.5)
    raise RuntimeError(f"API not reachable at {API}: {last_err}")


def _multipart_body(files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = "----ArlesPrDemoBoundary7MA4YWxkTrZu0gW"
    chunks: list[bytes] = []
    for rel, path in files:
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{rel}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
        chunks.append(header)
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def _collect_fixture(root: Path) -> list[tuple[str, Path]]:
    if not root.is_dir():
        raise FileNotFoundError(f"fixture not found: {root}")
    out: list[tuple[str, Path]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        out.append((rel, path))
    if not out:
        raise RuntimeError(f"fixture empty: {root}")
    return out


def _post_album(overwrite: bool = True) -> dict[str, Any]:
    body, boundary = _multipart_body(_collect_fixture(FIXTURE))
    query = urlencode({"overwrite": "true" if overwrite else "false"})
    req = urllib.request.Request(
        f"{API}/api/jobs?{query}",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST /api/jobs failed: {exc.code} {detail}") from exc


def _wait_job(job_id: str, timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = _get(f"/api/jobs/{job_id}")
        status = str(last.get("status") or "")
        if status in {"done", "failed", "cancelled"}:
            return last
        time.sleep(0.4)
    raise RuntimeError(f"job {job_id} did not finish: {last.get('status')}")


def _compose(*args: str) -> None:
    cmd = ["docker", "compose", *args]
    subprocess.run(cmd, cwd=str(COMPOSE_DIR), check=True)


def _seed_validate(*, preview_job_id: str = "") -> dict[str, Any]:
    script = Path(__file__).resolve().parent / "seed_validate_store.py"
    remote = "/tmp/seed_validate_store.py"
    _compose("cp", str(script), f"backend:{remote}")
    preview_id = preview_job_id or os.environ.get("ARLES_DEMO_PREVIEW_ID", "")
    # Prefer `env PYTHONPATH=…` so imports resolve to /app/src (not a stale
    # site-packages copy of the src package inside the image).
    result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "-e",
            f"ARLES_DEMO_VALIDATE_URL={os.environ.get('ARLES_DEMO_VALIDATE_URL', 'https://example.com/gallery/')}",
            "-e",
            "ARLES_DEMO_STATE=/tmp/arles-pr-demo-state.json",
            "-e",
            f"ARLES_DEMO_PREVIEW_ID={preview_id}",
            "backend",
            "env",
            "PYTHONPATH=/app",
            "python",
            remote,
        ],
        cwd=str(COMPOSE_DIR),
        check=True,
        capture_output=True,
        text=True,
    )
    line = (result.stdout or "").strip().splitlines()[-1]
    return json.loads(line)


def main() -> int:
    print(f"Waiting for API at {API} …")
    _wait_api()
    print(f"Uploading fixture {FIXTURE} …")
    created = _post_album(overwrite=True)
    job_id = str(created.get("id") or "")
    if not job_id:
        raise RuntimeError(f"create response missing id: {created}")
    detail = _wait_job(job_id)
    if detail.get("status") != "done":
        raise RuntimeError(
            f"preview job ended {detail.get('status')}: {detail.get('error')}"
        )
    title = ((detail.get("preview") or {}) or {}).get("title") or ""
    if MINI_TITLE not in str(title):
        print(f"warning: unexpected title {title!r} (expected {MINI_TITLE!r})", file=sys.stderr)

    state: dict[str, Any] = {
        "preview_job_id": job_id,
        "preview_title": title,
        "fixture": str(FIXTURE),
        "api": API,
    }

    if not SKIP_VALIDATE:
        print("Seeding fabricated validate report in JobStore …")
        validate = _seed_validate(preview_job_id=job_id)
        state.update(validate)
        if validate.get("preview_job_id"):
            state["preview_job_id"] = validate["preview_job_id"]
        if not SKIP_RESTART:
            print("Restarting backend so JobStore cache reloads …")
            _compose("restart", "backend")
            _wait_api()
            # Confirm the seeded validate job is visible.
            vid = str(state.get("validate_job_id") or "")
            if vid:
                report = _get(f"/api/jobs/{vid}")
                if not report.get("validation_report"):
                    raise RuntimeError(
                        f"validate job {vid} missing validation_report after restart"
                    )

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(state, indent=2))
    print(f"wrote {STATE_PATH}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or exc.stdout or str(exc), file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
