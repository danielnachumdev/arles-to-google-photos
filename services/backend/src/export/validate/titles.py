"""Title-id collision handling for validation indexes."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple


def identity_key(title: Optional[str]) -> Optional[str]:
    if title is None:
        return None
    stripped = str(title).strip()
    return stripped or None


def assign_title_ids(
    titles: List[Optional[str]],
) -> Tuple[List[str], List[str]]:
    """Map discovery/list order titles to unique title_ids.

    Duplicates on the same side get ``#2``, ``#3``, … suffixes.
    Returns ``(title_ids, warnings)``.
    """
    counts: Dict[str, int] = {}
    ids: List[str] = []
    warnings: List[str] = []
    for raw in titles:
        base = identity_key(raw) or "(untitled)"
        n = counts.get(base, 0) + 1
        counts[base] = n
        if n == 1:
            title_id = base
        else:
            title_id = f"{base} #{n}"
            warnings.append(f"Duplicate title on same side: {base!r} → {title_id}")
        ids.append(title_id)
    return ids, warnings
