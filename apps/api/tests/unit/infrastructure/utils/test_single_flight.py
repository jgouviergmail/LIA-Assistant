"""The coalescing seam: what it guarantees, and what it deliberately does not."""

from __future__ import annotations

import asyncio
import threading

import pytest

from src.infrastructure.utils import single_flight
from src.infrastructure.utils.single_flight import (
    in_flight_count,
    run_single_flight,
)

# asyncio_mode = "auto" (pyproject): an explicit asyncio mark here would also
# be applied to the synchronous helpers and warn.
pytestmark = [pytest.mark.unit]


class Work:
    """Instrumented work: counts its runs and can be made to fail or hang."""

    def __init__(self, *, delay: float = 0.02, fail: Exception | None = None) -> None:
        self.runs = 0
        self._delay = delay
        self._fail = fail

    async def __call__(self) -> str:
        self.runs += 1
        nth = self.runs
        await asyncio.sleep(self._delay)
        if self._fail is not None:
            raise self._fail
        return f"result#{nth}"


@pytest.fixture(autouse=True)
def _registry_is_clean() -> None:
    """Every test starts and ends with an empty registry."""
    assert in_flight_count() == 0


# =============================================================================
# What it guarantees
# =============================================================================


async def test_concurrent_callers_run_the_work_once() -> None:
    work = Work()
    results = await asyncio.gather(*(run_single_flight("k", work) for _ in range(5)))
    assert work.runs == 1
    assert [r.value for r in results] == ["result#1"] * 5
    assert [r.joined for r in results] == [False, True, True, True, True]


async def test_every_caller_gets_the_same_object() -> None:
    """Sharing the VALUE, not merely an equal one — the property a caller
    relies on when two responses must describe the same thing."""

    async def _build() -> list[int]:
        await asyncio.sleep(0.01)
        return [1, 2, 3]

    first, second = await asyncio.gather(
        run_single_flight("k", _build), run_single_flight("k", _build)
    )
    assert first.value is second.value


async def test_distinct_keys_do_not_share() -> None:
    work = Work()
    await asyncio.gather(run_single_flight("a", work), run_single_flight("b", work))
    assert work.runs == 2


async def test_the_registry_is_released_after_success() -> None:
    await run_single_flight("k", Work())
    assert in_flight_count() == 0


# =============================================================================
# What it deliberately is NOT
# =============================================================================


async def test_a_finished_flight_is_never_handed_to_a_later_caller() -> None:
    """It coalesces work in flight; it is not a cache. Answering "is this
    still true?" belongs to the caller's own cache."""
    work = Work()
    first = await run_single_flight("k", work)
    second = await run_single_flight("k", work)
    assert work.runs == 2
    assert (first.value, second.value) == ("result#1", "result#2")
    assert second.joined is False


# =============================================================================
# Cancellation
# =============================================================================


async def test_a_cancelled_waiter_does_not_kill_the_flight() -> None:
    """One client disconnecting must not take down the work the others need."""
    work = Work(delay=0.05)
    owner = asyncio.create_task(run_single_flight("k", work))
    await asyncio.sleep(0)
    waiter = asyncio.create_task(run_single_flight("k", work))
    await asyncio.sleep(0.01)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    result = await owner
    assert result.value == "result#1"
    assert work.runs == 1


async def test_a_cancelled_owner_does_not_strand_the_waiters() -> None:
    """The caller that started the flight is only a waiter like the others."""
    work = Work(delay=0.05)
    owner = asyncio.create_task(run_single_flight("k", work))
    await asyncio.sleep(0)
    waiter = asyncio.create_task(run_single_flight("k", work))
    await asyncio.sleep(0.01)
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner
    result = await waiter
    assert result.value == "result#1"
    assert result.joined is True
    assert work.runs == 1


async def test_the_registry_is_released_even_when_every_caller_left() -> None:
    work = Work(delay=0.03)
    owner = asyncio.create_task(run_single_flight("k", work))
    await asyncio.sleep(0)
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner
    # The shielded task survives its callers; the registry frees itself when
    # it finishes, never before.
    await asyncio.sleep(0.06)
    assert in_flight_count() == 0


# =============================================================================
# Failure
# =============================================================================


async def test_a_failure_reaches_every_caller() -> None:
    work = Work(fail=RuntimeError("boom"))
    outcomes = await asyncio.gather(
        run_single_flight("k", work),
        run_single_flight("k", work),
        return_exceptions=True,
    )
    assert work.runs == 1
    assert all(isinstance(o, RuntimeError) for o in outcomes)


async def test_a_failure_is_not_remembered() -> None:
    """The next caller retries rather than inheriting a poisoned result."""
    failing = Work(fail=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        await run_single_flight("k", failing)
    assert in_flight_count() == 0
    healthy = Work()
    result = await run_single_flight("k", healthy)
    assert result.value == "result#1"


# =============================================================================
# Event-loop hygiene (the registry is module-level and outlives a loop)
# =============================================================================


async def test_an_entry_from_another_loop_is_treated_as_absent() -> None:
    """A leftover from another loop must never be awaited from this one: it
    is a future that could not possibly complete here.

    The entry is planted directly, because reaching this state through the
    public seam would mean abandoning a pending task on a loop that is then
    closed — and an orphaned task is itself a test failure in this codebase.
    The task planted here is FINISHED, which is why the loop check has to come
    before the completion check: a foreign task is unusable either way.
    """
    stale = _finished_task_from_a_closed_loop()
    single_flight._FLIGHTS["cross-loop"] = stale
    try:
        fresh = Work()
        result = await run_single_flight("cross-loop", fresh)
        assert result.joined is False, "a foreign entry was mistaken for a live flight"
        assert result.value == "result#1"
    finally:
        single_flight._FLIGHTS.pop("cross-loop", None)


def _finished_task_from_a_closed_loop() -> asyncio.Task[str]:
    """A completed task bound to a loop that no longer exists — no orphan.

    Built in its own thread: a second loop cannot be driven from a thread
    that is already running one, which is the very situation this guard is
    there to survive.
    """
    holder: dict[str, asyncio.Task[str]] = {}

    async def _noop() -> str:
        return "stale"

    async def _run() -> None:
        holder["task"] = asyncio.create_task(_noop())
        await holder["task"]

    def _drive() -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()

    thread = threading.Thread(target=_drive, name="stale-loop")
    thread.start()
    thread.join()
    return holder["task"]
