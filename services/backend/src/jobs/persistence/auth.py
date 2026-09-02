"""Resolve the authenticated email from oauth2-proxy / nginx identity headers."""
from __future__ import annotations

from typing import Mapping, Optional

LOCAL_DEV_EMAIL = "local@localhost"

# Prefer oauth2-proxy auth_request headers; accept common proxies as fallback.
_EMAIL_HEADERS = (
    "x-auth-request-email",
    "x-forwarded-email",
    "x-user",
)


class IdentityError(ValueError):
    """No usable identity for a non-local request."""


def _header(headers: Mapping[str, str], name: str) -> str:
    # Starlette headers are case-insensitive; Mapping may be plain dict.
    lowered = {str(k).lower(): str(v) for k, v in headers.items()}
    return str(lowered.get(name.lower(), "") or "").strip()


def resolve_request_email(
    headers: Mapping[str, str],
    *,
    app_env: str,
) -> str:
    """Return normalized email for the request.

    ``APP_ENV=local`` (aliases handled by caller) may omit headers and falls
    back to ``LOCAL_DEV_EMAIL`` so compose / pytest keep working. Cloud
    (gated) requests without an identity header fail closed.
    """
    for name in _EMAIL_HEADERS:
        value = _header(headers, name)
        if value:
            return value.lower()
    env = str(app_env or "").strip().lower()
    if env in {"local", "dev", "development"}:
        return LOCAL_DEV_EMAIL
    raise IdentityError("missing authenticated email identity header")
