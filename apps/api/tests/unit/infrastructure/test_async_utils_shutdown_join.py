"""A shutdown waits for the tasks it cancels (audit A05).

``wait_all_background_tasks`` cancelled the tasks still running at its timeout and
returned at once: their cancellation — the ``finally`` that releases a claim, closes a
file or writes a final status — then ran after the shutdown had gone on to close the
pools it needs, or not at all once the loop stopped (reproduced 2026-10-22). The wait now
joins what it cancelled, within a bound of its own, and names a task that will not stop.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Iterator

import pytest
import structlog

from src.infrastructure import async_utils
from tests.support.structlog_capture import fresh_module_logger

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_module_logger() -> Iterator[None]:
    """Keep ``capture_logs`` reliable once the application logger is frozen (full-suite runs)."""
    yield from fresh_module_logger(async_utils)


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> set[asyncio.Task[None]]:
    """The module's registry of background tasks, empty for this test."""
    tasks: set[asyncio.Task[None]] = set()
    monkeypatch.setattr(async_utils, "_background_tasks", tasks)
    return tasks


async def test_a_cancelled_task_has_finished_its_cleanup_when_the_wait_returns(
    registry: set[asyncio.Task[None]],
) -> None:
    cleaned: list[str] = []
    started = asyncio.Event()

    async def worker() -> None:
        started.set()
        try:
            await asyncio.sleep(3600)
        finally:
            await asyncio.sleep(0.05)  # a cleanup that itself waits: a close, a last write
            cleaned.append("released")

    task = asyncio.create_task(worker())
    registry.add(task)
    await started.wait()

    await async_utils.wait_all_background_tasks(timeout=0.01)

    assert cleaned == ["released"]
    assert task.cancelled()


async def test_a_task_that_will_not_stop_is_named_and_the_wait_stays_bounded(
    registry: set[asyncio.Task[None]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(async_utils, "BACKGROUND_TASKS_CANCEL_JOIN_TIMEOUT_S", 0.1)
    release = asyncio.Event()

    async def stubborn() -> None:
        while not release.is_set():
            # Swallowing every cancellation is the defect this names.
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.sleep(3600)

    task = asyncio.create_task(stubborn(), name="stubborn_sweep")
    registry.add(task)
    await asyncio.sleep(0)

    with structlog.testing.capture_logs() as captured:
        started = time.monotonic()
        await async_utils.wait_all_background_tasks(timeout=0.01)
        waited = time.monotonic() - started

    release.set()
    task.cancel()
    await asyncio.wait({task}, timeout=1)
    not_joined = [entry for entry in captured if entry["event"] == "background_tasks_not_joined"]
    assert waited < 2, "the wait outlived its own bound"
    assert len(not_joined) == 1
    assert not_joined[0]["task_names"] == ["stubborn_sweep"]


async def test_cancelling_the_shutdown_itself_is_never_swallowed(
    registry: set[asyncio.Task[None]],
) -> None:
    task = asyncio.create_task(asyncio.sleep(3600))
    registry.add(task)
    shutdown = asyncio.create_task(async_utils.wait_all_background_tasks(timeout=30))
    await asyncio.sleep(0.01)

    shutdown.cancel()

    with pytest.raises(asyncio.CancelledError):
        await shutdown
    task.cancel()
    await asyncio.wait({task}, timeout=1)
