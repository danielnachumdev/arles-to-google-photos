"""In-memory Google token vault is never durable."""
from __future__ import annotations

from tests.support.suites import TokenVaultSuite


class TestAccessTokenVault(TokenVaultSuite):
    def test_vault_put_pop_and_discard(self) -> None:
        self.vault.put("job-1", "  ya29.tok  ")
        assert self.vault.get("job-1") == "ya29.tok"
        assert self.vault.pop("job-1") == "ya29.tok"
        assert self.vault.get("job-1") is None
        assert self.vault.pop("job-1") is None

        self.vault.put("job-2", "ya29.keep")
        self.vault.discard("job-2")
        assert self.vault.get("job-2") is None

    def test_vault_ignores_blank_tokens(self) -> None:
        self.vault.put("job-1", "   ")
        self.vault.put("", "ya29.tok")
        assert self.vault.get("job-1") is None
        assert self.vault.get("") is None
