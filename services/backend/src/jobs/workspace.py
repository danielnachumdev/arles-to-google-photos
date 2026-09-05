"""Write an uploaded album tree onto disk and apply timestamps."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from gp_wrapper.utils import FileTime, FileTimeService


class JobWorkspace:
    """Materialize an uploaded album file tree under a single root directory."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def materialize(
        self,
        files: Iterable[tuple[str, bytes, Optional[float]]],
    ) -> Path:
        """Write files under ``self.root``.

        Relpaths must stay inside the root (``..`` and absolute paths are
        rejected). Parent directories are created as needed. When
        ``last_modified`` is set, apply access and modification times via
        ``FileTimeService``.
        """
        # Stream one file at a time — do not buffer the whole album in memory.
        self.root.mkdir(parents=True, exist_ok=True)
        times = FileTimeService()
        for relpath, payload, last_modified in files:
            dest = self._resolve_inside_root(relpath)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(payload)
            if last_modified is not None:
                stamp = datetime.fromtimestamp(last_modified)
                times.set(
                    str(dest),
                    FileTime(access=stamp, modification=stamp),
                )
        return self.root

    def _resolve_inside_root(self, relpath: str) -> Path:
        normalized = relpath.replace("\\", "/")
        if Path(normalized).is_absolute():
            raise ValueError(f"path traversal: {relpath}")
        parts = [part for part in normalized.split("/") if part and part != "."]
        if not parts or any(part == ".." for part in parts):
            raise ValueError(f"path traversal: {relpath}")
        root = self.root.resolve()
        dest = root.joinpath(*parts).resolve()
        try:
            dest.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path traversal: {relpath}") from exc
        if dest == root:
            raise ValueError(f"path traversal: {relpath}")
        return dest
