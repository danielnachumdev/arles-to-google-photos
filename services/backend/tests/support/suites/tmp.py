"""Per-test tmp_path binding. Not collected (no Test prefix)."""
from __future__ import annotations

from pathlib import Path

import pytest


class TmpPathSuite:
    """Bind pytest ``tmp_path`` onto ``self`` (xdist-safe, per test).

    Uses an autouse fixture (not ``setup_method``) so ``self.tmp_path`` is
    available before any other fixture/setup on the subclass.
    """

    tmp_path: Path

    @pytest.fixture(autouse=True)
    def _bind_tmp_path(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
