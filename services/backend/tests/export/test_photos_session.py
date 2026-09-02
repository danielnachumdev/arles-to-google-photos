"""TDD: GooglePhotos session from a frontend access token."""
from __future__ import annotations

import pytest

from src.export.photos_session import google_photos_from_access_token


class TestPhotosSession:
    def test_token_session_uses_supplied_bearer(self) -> None:
        gp = google_photos_from_access_token("  ya29.abc  ")
        assert gp.credentials.token == "ya29.abc"
        assert gp.session is not None

    def test_empty_token_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="access_token"):
            google_photos_from_access_token("   ")
