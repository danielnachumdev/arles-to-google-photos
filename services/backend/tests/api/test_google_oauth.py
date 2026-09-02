"""TDD: load public Google OAuth client id and Photos scopes."""
from __future__ import annotations

import json

from src.api.google_oauth import load_google_oauth_client_id, photos_scope_list
from tests.support.suites import OAuthSecretsSuite


class TestGoogleOauthConfig(OAuthSecretsSuite):
    def test_photos_scopes_match_gp_wrapper(self) -> None:
        scopes = photos_scope_list()
        assert scopes == [
            "https://www.googleapis.com/auth/photoslibrary",
            "https://www.googleapis.com/auth/photoslibrary.appendonly",
            "https://www.googleapis.com/auth/photoslibrary.sharing",
            "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata",
        ]

    def test_env_client_id_wins(self) -> None:
        self.write_secrets({"web": {"client_id": "from-file.apps.googleusercontent.com"}})
        self.monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "from-env.apps.googleusercontent.com")
        assert load_google_oauth_client_id() == "from-env.apps.googleusercontent.com"

    def test_empty_env_client_id_falls_back_to_file(self) -> None:
        self.write_secrets({"web": {"client_id": "from-file.apps.googleusercontent.com"}})
        self.monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "   ")
        self.monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS", "")
        self.monkeypatch.setenv("GOOGLE_CLIENT_SECRETS_JSON", "")
        assert load_google_oauth_client_id() == "from-file.apps.googleusercontent.com"

    def test_json_env_without_file(self) -> None:
        self.missing_secrets()
        self.monkeypatch.setenv(
            "GOOGLE_OAUTH_CLIENT_SECRETS",
            json.dumps(
                {
                    "web": {
                        "client_id": "json-env.apps.googleusercontent.com",
                        "client_secret": "must-not-leak",
                    }
                }
            ),
        )
        assert load_google_oauth_client_id() == "json-env.apps.googleusercontent.com"

    def test_json_env_alias_client_secrets_json(self) -> None:
        self.missing_secrets()
        self.monkeypatch.setenv(
            "GOOGLE_CLIENT_SECRETS_JSON",
            json.dumps(
                {"web": {"client_id": "alias-json.apps.googleusercontent.com"}}
            ),
        )
        assert load_google_oauth_client_id() == "alias-json.apps.googleusercontent.com"

    def test_env_client_id_wins_over_json_env(self) -> None:
        self.missing_secrets()
        self.monkeypatch.setenv(
            "GOOGLE_OAUTH_CLIENT_SECRETS",
            json.dumps({"web": {"client_id": "json-env.apps.googleusercontent.com"}}),
        )
        self.monkeypatch.setenv(
            "GOOGLE_OAUTH_CLIENT_ID", "explicit.apps.googleusercontent.com"
        )
        assert load_google_oauth_client_id() == "explicit.apps.googleusercontent.com"

    def test_json_env_wins_over_file(self) -> None:
        self.write_secrets({"web": {"client_id": "from-file.apps.googleusercontent.com"}})
        self.monkeypatch.setenv(
            "GOOGLE_OAUTH_CLIENT_SECRETS",
            json.dumps({"web": {"client_id": "json-env.apps.googleusercontent.com"}}),
        )
        assert load_google_oauth_client_id() == "json-env.apps.googleusercontent.com"

    def test_invalid_json_env_does_not_fall_back_to_file(self) -> None:
        self.write_secrets({"web": {"client_id": "from-file.apps.googleusercontent.com"}})
        self.monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS", "{not json")
        assert load_google_oauth_client_id() is None

    def test_web_client_secrets_file(self) -> None:
        self.write_secrets(
            {
                "web": {
                    "client_id": "web.apps.googleusercontent.com",
                    "client_secret": "not-for-frontend",
                }
            }
        )
        assert load_google_oauth_client_id() == "web.apps.googleusercontent.com"

    def test_missing_secrets_returns_none(self) -> None:
        self.missing_secrets()
        assert load_google_oauth_client_id() is None

    def test_invalid_json_returns_none(self) -> None:
        self.write_secrets("{not json")
        assert load_google_oauth_client_id() is None

    def test_non_object_json_returns_none(self) -> None:
        self.write_secrets(["web"])
        assert load_google_oauth_client_id() is None

    def test_installed_client_id_is_accepted(self) -> None:
        self.write_secrets(
            {"installed": {"client_id": "installed.apps.googleusercontent.com"}}
        )
        assert load_google_oauth_client_id() == "installed.apps.googleusercontent.com"

    def test_missing_client_id_in_block_returns_none(self) -> None:
        self.write_secrets({"web": {"client_secret": "x"}})
        assert load_google_oauth_client_id() is None

    def test_non_dict_web_block_returns_none(self) -> None:
        self.write_secrets({"web": "not-a-block"})
        assert load_google_oauth_client_id() is None
