"""A durable write in a ``finally`` must run ONCE, not twice (ADR-263).

This helper exists because both halves of the problem were measured, and the
second one only surfaced under an adversarial review.

1. A write in a ``finally`` runs while a cancellation is already propagating,
   so a plain ``await`` is cut short and the row is lost.
2. ``asyncio.shield`` fixes the FIRST delivery — but a cancellation can be
   re-delivered, and shielding a FRESH coroutine per attempt runs the write
   again. Simulated: ``['start', 'start', 'done', 'done']``. For the decision
   register that meant one turn upserted twice, its ``segments`` counter
   reading 2 for a turn nobody interrupted.

So the work becomes a task ONCE and every attempt awaits that same task. These
tests pin both properties, because a paraphrase of this dance has already
regressed it once.
"""

from __future__ import annotations

import asyncio

import pytest

from src.infrastructure.async_utils import write_through_cancellation

pytestmark = [pytest.mark.unit]


class TestTheWriteRunsExactlyOnce:
    async def test_an_uncancelled_write_runs_once_and_reports_no_cancellation(self) -> None:
        calls: list[str] = []

        async def write() -> None:
            calls.append("run")

        cancelled = await write_through_cancellation(write, attempts=3, label="probe")

        assert calls == ["run"]
        assert cancelled is False

    async def test_a_RE_DELIVERED_cancellation_does_not_write_twice(self) -> None:
        """The exact regression this helper was extracted to prevent."""
        calls: list[str] = []

        async def write() -> None:
            calls.append("start")
            await asyncio.sleep(0.05)
            calls.append("done")

        async def caller() -> bool:
            return await write_through_cancellation(write, attempts=3, label="probe")

        task = asyncio.create_task(caller())
        await asyncio.sleep(0.01)
        task.cancel()
        cancelled = await task
        await asyncio.sleep(0.1)

        assert calls.count("start") == 1, f"the write ran {calls.count('start')} times"
        assert calls.count("done") == 1, "the single write did not complete"
        assert cancelled is True, "the caller must learn it was cancelled"

    async def test_the_write_COMPLETES_despite_the_cancellation(self) -> None:
        """Losing the row is the failure this whole helper exists to prevent."""
        written: list[str] = []

        async def write() -> None:
            await asyncio.sleep(0.05)
            written.append("row")

        async def caller() -> bool:
            return await write_through_cancellation(write, attempts=3, label="probe")

        task = asyncio.create_task(caller())
        await asyncio.sleep(0.01)
        task.cancel()
        await task

        assert written == ["row"]


class TestItNeverHoldsAShutdownOpen:
    async def test_a_write_that_never_ends_is_ABANDONED_after_its_attempts(self) -> None:
        started = asyncio.Event()

        async def write() -> None:
            started.set()
            await asyncio.sleep(60)

        async def caller() -> bool:
            return await write_through_cancellation(write, attempts=2, label="probe")

        task = asyncio.create_task(caller())
        await started.wait()
        for _ in range(4):
            task.cancel()
            await asyncio.sleep(0)

        assert await asyncio.wait_for(task, timeout=1.0) is True

    async def test_an_ABANDONED_write_is_still_referenced_while_it_finishes(self) -> None:
        # The abandonment path returns while the write is still running. Its
        # only local reference goes out of scope at that moment, and asyncio
        # holds tasks weakly — so without an explicit strong reference the row
        # can be collected mid-write, which is the exact failure this module's
        # ``safe_fire_and_forget`` exists to prevent.
        from src.infrastructure.async_utils import _background_tasks

        release = asyncio.Event()
        started = asyncio.Event()

        async def write() -> None:
            started.set()
            await release.wait()

        async def caller() -> bool:
            return await write_through_cancellation(write, attempts=1, label="probe")

        task = asyncio.create_task(caller())
        await started.wait()
        for _ in range(3):
            task.cancel()
            await asyncio.sleep(0)
        assert await asyncio.wait_for(task, timeout=1.0) is True

        held = [one for one in _background_tasks if one.get_name() == "probe"]
        assert held, "an abandoned write must be held by a strong reference"

        release.set()
        await asyncio.wait_for(asyncio.gather(*held), timeout=1.0)
        await asyncio.sleep(0)
        assert not [one for one in _background_tasks if one.get_name() == "probe"]

    async def test_a_completed_write_leaves_nothing_behind(self) -> None:
        from src.infrastructure.async_utils import _background_tasks

        async def write() -> None:
            return None

        assert await write_through_cancellation(write, attempts=2, label="probe") is False
        await asyncio.sleep(0)
        assert not [one for one in _background_tasks if one.get_name() == "probe"]

    async def test_a_factory_is_required_rather_than_an_awaitable(self) -> None:
        """A coroutine is awaitable exactly once (Systemic Rules): a seam given
        one could not decide whether to run it, only whether to fail."""
        import inspect

        signature = inspect.signature(write_through_cancellation)

        assert list(signature.parameters) == ["make_write", "attempts", "label"]
        assert signature.parameters["attempts"].kind is inspect.Parameter.KEYWORD_ONLY


class TestAFailureIsTheCallerSToSee:
    async def test_the_write_s_exception_reaches_the_caller(self) -> None:
        """The helper does not swallow: each register decides what a lost row
        costs, and both choose to log rather than take the turn down."""

        async def write() -> None:
            raise RuntimeError("the register is unwritable")

        with pytest.raises(RuntimeError, match="unwritable"):
            await write_through_cancellation(write, attempts=3, label="probe")
