"""A bounded waiter must not erase a run's still-live background tasks."""

import asyncio
from uuid import uuid4

import pytest

from src.infrastructure.async_utils import await_run_id_tasks, safe_fire_and_forget

pytestmark = pytest.mark.unit


async def test_timeout_keeps_the_live_task_visible_to_the_next_waiter() -> None:
    """A timeout reports waiting, not completion or loss of task ownership."""
    run_id = str(uuid4())
    entered = asyncio.Event()
    finish = asyncio.Event()

    async def writer() -> None:
        entered.set()
        await finish.wait()

    task = safe_fire_and_forget(writer(), name="owned-test-writer", run_id=run_id)
    try:
        await entered.wait()
        assert await await_run_id_tasks(run_id, timeout=0) == 1
        assert not task.done()
        assert await await_run_id_tasks(run_id, timeout=0) == 1
    finally:
        finish.set()
        await task
        await await_run_id_tasks(run_id, timeout=0)


async def test_cancelling_a_waiter_does_not_cancel_or_hide_its_writer() -> None:
    """The waiting request does not own the independently registered work."""
    run_id = str(uuid4())
    finish = asyncio.Event()
    writer = safe_fire_and_forget(finish.wait(), name="independent-writer", run_id=run_id)
    waiter = asyncio.create_task(await_run_id_tasks(run_id))
    try:
        await asyncio.sleep(0)  # Let the waiter enter asyncio.wait, no elapsed-time oracle.
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert not writer.done()
        assert await await_run_id_tasks(run_id, timeout=0) == 1
    finally:
        finish.set()
        await writer


async def test_a_task_added_during_the_wait_keeps_its_own_lifetime() -> None:
    """An earlier snapshot's completion never drops a later writer."""
    run_id = str(uuid4())
    first_end, second_end = asyncio.Event(), asyncio.Event()
    first = safe_fire_and_forget(first_end.wait(), run_id=run_id)
    waiter = asyncio.create_task(await_run_id_tasks(run_id))
    await asyncio.sleep(0)
    second = safe_fire_and_forget(second_end.wait(), run_id=run_id)
    try:
        first_end.set()
        assert await waiter == 1
        assert not second.done()
        assert await await_run_id_tasks(run_id, timeout=0) == 1
    finally:
        first_end.set()
        second_end.set()
        await asyncio.gather(first, second, waiter)
