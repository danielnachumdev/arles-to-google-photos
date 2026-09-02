"""Public Google OAuth client id + Photos scopes for frontend sign-in."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

PHOTOS_SCOPES: Tuple[str, ...] = (
    "https://www.googleapis.com/auth/photoslibrary",
    "https://www.googleapis.com/auth/photoslibrary.appendonly",
    "https://www.googleapis.com/auth/photoslibrary.sharing",
    "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata",
)

# Full client_secrets.json text (Secret Manager). Not the file path env.
_JSON_SECRETS_ENV_VARS: Tuple[str, ...] = (
    "GOOGLE_OAUTH_CLIENT_SECRETS",
    "GOOGLE_CLIENT_SECRETS_JSON",
)
_DEFAULT_SECRETS_FILE = "client_secrets.json"


def _env_nonempty(name: str) -> str:
    return os.environ.get(name, "").strip()


def _client_id_from_secrets_mapping(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    block = data.get("web") or data.get("installed") or {}
    if not isinstance(block, dict):
        return None
    client_id = str(block.get("client_id") or "").strip()
    return client_id or None


def _client_id_from_json_text(raw: str) -> Optional[str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return _client_id_from_secrets_mapping(data)


def _client_id_from_json_env() -> Tuple[Optional[str], bool]:
    """Parse JSON env. Return (client_id, saw_nonempty_json_env)."""
    saw_json_env = False
    for name in _JSON_SECRETS_ENV_VARS:
        raw = _env_nonempty(name)
        if not raw:
            continue
        saw_json_env = True
        client_id = _client_id_from_json_text(raw)
        if client_id:
            return client_id, True
    return None, saw_json_env


def _client_id_from_file(secrets_path: Optional[Path]) -> Optional[str]:
    if secrets_path is not None:
        path = secrets_path
    else:
        path_env = _env_nonempty("GOOGLE_CLIENT_SECRETS")
        path = Path(path_env or _DEFAULT_SECRETS_FILE)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _client_id_from_secrets_mapping(data)


def load_google_oauth_client_id(
    secrets_path: Optional[Path] = None,
) -> Optional[str]:
    env_id = _env_nonempty("GOOGLE_OAUTH_CLIENT_ID")
    if env_id:
        return env_id
    json_id, json_env_set = _client_id_from_json_env()
    if json_id:
        return json_id
    if json_env_set:
        return None
    return _client_id_from_file(secrets_path)


def photos_scope_list() -> List[str]:
    return list(PHOTOS_SCOPES)
