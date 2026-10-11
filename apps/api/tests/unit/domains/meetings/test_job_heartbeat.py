"""Losing a live owner cancels work instead of waiting for an obsolete result."""

import asyncio
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


async def test_missing_owner_never_starts_work() -> None:
    from src.domains.meetings.job_heartbeat import run_with_heartbeats

    work = AsyncMock(return_value="result")
    with pytest.raises(PermissionError):
        await run_with_heartbeats(work, AsyncMock(side_effect=PermissionError()), 0.001)
    work.assert_not_called()


async def test_lost_owner_cancels_inflight_work() -> None:
    from src.domains.meetings.job_heartbeat import run_with_heartbeats

    cancelled = asyncio.Event()
    calls = 0

    async def guard() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError()

    async def work() -> str:
        try:
            await asyncio.Event().wait()
            return "never"
        finally:
            cancelled.set()

    with pytest.raises(PermissionError):
        await asyncio.wait_for(run_with_heartbeats(work, guard, 0.001), 2)
    assert cancelled.is_set()


async def test_completed_result_is_checked_again() -> None:
    from src.domains.meetings.job_heartbeat import run_with_heartbeats

    guard = AsyncMock()
    assert await run_with_heartbeats(AsyncMock(return_value="result"), guard, 1) == "result"
    assert guard.await_count == 2
