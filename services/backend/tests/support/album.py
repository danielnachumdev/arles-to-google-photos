"""SRP helper: load fixture album trees as file tuples or multipart uploads."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from tests.conftest import DAY1_ARLES, DAY1_MINI

FileTuple = Tuple[str, bytes, Optional[float]]

_MINI_RELS = (
    "index.html",
    "hrimages/20120802_01hr.JPG",
    "imagepages/20120802_01.html",
)
_ARLES_RELS = (
    "index.html",
    "hrimages/20120802_01hr.JPG",
    "hrimages/20120802_02hr.JPG",
    "hrimages/Text.jpg",
    "hrimages/aaa.jpg",
    "imagepages/20120802_01.html",
    "imagepages/20120802_02.html",
    "imagepages/Text.html",
)


class AlbumTree:
    """Read parser-compatible fixture albums without copying relpath lists."""

    @staticmethod
    def tuples_from(root: Path, rels: Sequence[str]) -> List[FileTuple]:
        return [(rel, (root / rel).read_bytes(), None) for rel in rels]

    @staticmethod
    def multipart_from(
        root: Path,
        rels: Sequence[str],
        *,
        content_type: str = "application/octet-stream",
    ) -> list:
        return [
            ("files", (rel, (root / rel).read_bytes(), content_type)) for rel in rels
        ]

    @classmethod
    def mini_tuples(cls) -> List[FileTuple]:
        return cls.tuples_from(DAY1_MINI, _MINI_RELS)

    @classmethod
    def mini_multipart(cls) -> list:
        return cls.multipart_from(DAY1_MINI, _MINI_RELS)

    @classmethod
    def arles_multipart(cls) -> list:
        return cls.multipart_from(DAY1_ARLES, _ARLES_RELS)

    @staticmethod
    def video_multipart(
        *,
        item_id: str = "0512_1_06[1]",
        title: str = "May video",
        caption: str = "clip",
        video: bytes | None = None,
        poster: bytes | None = None,
        play: bytes | None = None,
        include_sidecars: bool = True,
    ) -> list:
        """Synthetic leaf album with one video item (optional poster/mp4)."""
        index = (
            "<!DOCTYPE html>\n<html><body>\n"
            f'  <span class="gallerytitle">{title}</span>\n'
            f'  <a href="imagepages/{item_id}.html">\n'
            f'    <img src="thumbnails/TN_{item_id}.jpg">\n'
            "  </a>\n</body></html>\n"
        )
        page = (
            f'<html><body><div class="imagetitle">{caption}</div></body></html>'
        )
        files = [
            ("files", ("index.html", index.encode("utf-8"), "text/html")),
            (
                "files",
                (
                    f"imagepages/{item_id}.html",
                    page.encode("utf-8"),
                    "text/html",
                ),
            ),
            (
                "files",
                (
                    f"hrimages/{item_id}hr.wmv",
                    video if video is not None else b"WMV" + b"V" * 256,
                    "video/x-ms-wmv",
                ),
            ),
        ]
        if include_sidecars:
            files.append(
                (
                    "files",
                    (
                        f"thumbnails/TN_{item_id}.jpg",
                        poster
                        if poster is not None
                        else b"\xff\xd8" + b"P" * 32 + b"\xff\xd9",
                        "image/jpeg",
                    ),
                )
            )
            files.append(
                (
                    "files",
                    (
                        f"preview/{item_id}.mp4",
                        play if play is not None else b"ftyp-fake-mp4",
                        "video/mp4",
                    ),
                )
            )
        return files
