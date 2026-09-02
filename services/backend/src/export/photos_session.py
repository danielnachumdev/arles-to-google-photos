"""Google Photos session backed by a browser-issued OAuth access token."""
from __future__ import annotations

import requests
from google.oauth2.credentials import Credentials
from gp_wrapper import GooglePhotos


def google_photos_from_access_token(access_token: str) -> GooglePhotos:
    token = (access_token or "").strip()
    if not token:
        raise ValueError("access_token is required")
    return AccessTokenGooglePhotos(token)


class AccessTokenGooglePhotos(GooglePhotos):
    """Skip InstalledAppFlow; use an access token from the frontend."""

    def __init__(self, access_token: str) -> None:
        self.credentials = Credentials(token=access_token)  # type: ignore[no-untyped-call]
        self.session = requests.Session()
        self.session.credentials = self.credentials  # type: ignore[attr-defined]
