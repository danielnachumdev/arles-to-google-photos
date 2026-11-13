"""AdaptiveWorkLane: shared cooldown pauses all workers on transient failure."""
from __future__ import annotations

import threading
import time
from typing import Callable, List

import pytest

from src.export.work_lane import AdaptiveWorkLane, TransientError


class _Transient(Exception):
    pass


class _Hard(Exception):
    pass


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, (_Transient, TransientError))


def test_map_preserves_order() -> None:
    lane = AdaptiveWorkLane(max_workers=4, is_transient=_is_transient)
    try:
        results = lane.map([lambda i=i: i * 2 for i in range(5)])
        assert results == [0, 2, 4, 6, 8]
    finally:
        lane.close()


def test_transient_failure_pauses_entire_lane() -> None:
    """When one task trips transient, peers wait for cooldown before starting."""
    started: List[float] = []
    lock = threading.Lock()
    first_entered = threading.Event()
    release_first = threading.Event()

    def first() -> str:
        first_entered.set()
        release_first.wait(timeout=2.0)
        raise _Transient("slow down")

    def second() -> str:
        with lock:
            started.append(time.monotonic())
        return "ok"

    lane = AdaptiveWorkLane(
        max_workers=2,
        is_transient=_is_transient,
        initial_backoff_s=0.25,
        max_backoff_s=0.25,
        max_retries=1,
    )
    try:
        f1 = lane.submit(first)
        assert first_entered.wait(timeout=2.0)
        f2 = lane.submit(second)
        # Second must not finish before first has tripped cooldown + slept.
        time.sleep(0.05)
        with lock:
            assert started == []
        t0 = time.monotonic()
        release_first.set()
        assert f2.result(timeout=5.0) == "ok"
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.2
        with pytest.raises(_Transient):
            f1.result(timeout=5.0)
    finally:
        lane.close()


def test_hard_failure_does_not_pause_lane() -> None:
    barrier = threading.Barrier(2)
    second_started = threading.Event()

    def boom() -> None:
        barrier.wait(timeout=2.0)
        raise _Hard("nope")

    def peer() -> str:
        barrier.wait(timeout=2.0)
        second_started.set()
        return "peer"

    lane = AdaptiveWorkLane(
        max_workers=2,
        is_transient=_is_transient,
        initial_backoff_s=2.0,
        max_retries=0,
    )
    try:
        f1 = lane.submit(boom)
        f2 = lane.submit(peer)
        assert second_started.wait(timeout=1.0)
        assert f2.result(timeout=2.0) == "peer"
        with pytest.raises(_Hard):
            f1.result(timeout=2.0)
    finally:
        lane.close()


def test_retries_transient_until_success() -> None:
    attempts = {"n": 0}

    def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TransientError("wait")
        return "done"

    lane = AdaptiveWorkLane(
        max_workers=1,
        is_transient=_is_transient,
        initial_backoff_s=0.01,
        max_backoff_s=0.05,
        max_retries=5,
    )
    try:
        assert lane.run(flaky) == "done"
        assert attempts["n"] == 3
    finally:
        lane.close()
