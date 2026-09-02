from __future__ import annotations

from typing import Iterable, TypeVar

T = TypeVar("T")


def batchify(objects: Iterable[T], batch_max_size: int) -> list[list[T]]:
    """Split an iterable into batches no larger than ``batch_max_size``."""
    batches: list[list[T]] = []
    batch: list[T] = []
    for obj in objects:
        batch.append(obj)
        if len(batch) == batch_max_size:
            batches.append(batch)
            batch = []
    if batch:
        batches.append(batch)
    return batches
