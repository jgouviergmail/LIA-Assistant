"""A lost conversation lock must stop the run that lost it.

The lease already owns the three moves a durable claim needs — acquire,
heartbeat, release by owner token. What it did not own is the consequence: the
heartbeat NOTICED the lock was gone, logged ``active_run_lock_lost``, and
returned. The block it was guarding kept running.

That is the state the lock exists to make impossible. Measured 2026-09-10 on
the shipped defaults: the TTL is 30 s and the heartbeat beats every 10 s, while
a ticket run lasts minutes — so a Redis blip longer than half a minute expires
the lock, the next chat message acquires the free key, and TWO producers write
to one conversation and one LangGraph thread. CLAUDE.md states the rule
plainly: « A failed heartbeat immediately aborts all later effects. »

Two outcomes are deliberately different:

- a lock that merely EXPIRED is nobody's, so the run RE-TAKES it and carries on
  — aborting a healthy run over a Redis hiccup would be the cure being worse;
- a lock somebody else now holds is a genuine takeover, and the block is
  aborted with :class:`ActiveRunLockLost` — a normal exception, because the
  only caller is a scheduler tick whose docstring says it never raises.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.infrastructure.streaming.run_stream_broker import (
    ActiveRunLockLost,
    active_run_lease,
    heartbeat_active_run,
)

pytestmark = pytest.mark.unit

CONVERSATION = "c-1"
RUN = "run-1"
STREAM = "workboard:run-1"


@pytest.fixture(autouse=True)
def _instant_beats(monkeypatch: pytest.MonkeyPatch) -> None:
    """Beat with no wall time: the loop is what is under test, not the clock."""
    monkeypatch.setattr(settings, "background_runs_heartbeat_seconds", 0, raising=False)


def _redis(*, refresh: Any, acquire: Any = True, retake: Any = True) -> AsyncMock:
    """A Redis whose lock answers exactly what a scenario needs.

    ``SET NX`` is asked TWICE in a lease that loses its lock — once to take it
    and once to re-take it — and the two answers are what separates « the key
    expired » from « somebody else holds it ». Conflating them is what made the
    first version of these tests assert on a lease that never acquired
    anything.

    Args:
        refresh: What ``EVAL`` returns — 1 keeps the lock, anything else loses it.
        acquire: What the FIRST ``SET NX`` returns (the lease's own take).
        retake: What every later ``SET NX`` returns (the heartbeat's re-take).

    Returns:
        The double.
    """
    redis = AsyncMock()
    redis.eval = AsyncMock(side_effect=refresh if callable(refresh) else lambda *_: refresh)
    answers = iter([acquire])

    async def _set(*_args: Any, **_kwargs: Any) -> Any:
        return next(answers, retake)

    redis.set = AsyncMock(side_effect=_set)
    return redis


class TestTheHeartbeatWhenTheLockGoesAway:
    async def test_a_lock_that_merely_expired_is_retaken(self) -> None:
        """A Redis blip must not cost a run that nobody else has claimed."""
        redis = _redis(refresh=0, acquire=True)
        lost = False

        def on_lost() -> None:
            nonlocal lost
            lost = True

        beat = asyncio.create_task(
            heartbeat_active_run(redis, CONVERSATION, STREAM, run_id=RUN, on_lost=on_lost)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        beat.cancel()
        with pytest.raises(asyncio.CancelledError):
            await beat

        assert redis.set.await_count >= 1, "the free key was never re-taken"
        assert lost is False, "a re-taken lock is not a loss"

    async def test_a_lock_somebody_else_holds_is_a_loss(self) -> None:
        redis = _redis(refresh=0, acquire=None, retake=None)
        lost = False

        def on_lost() -> None:
            nonlocal lost
            lost = True

        await asyncio.wait_for(
            heartbeat_active_run(redis, CONVERSATION, STREAM, run_id=RUN, on_lost=on_lost),
            timeout=2,
        )
        assert lost is True, "the takeover was never signalled"

    async def test_without_a_run_id_it_cannot_retake_and_says_so(self) -> None:
        """Re-taking needs the payload the lock stores; no id, no re-take."""
        redis = _redis(refresh=0, acquire=True)
        lost = False

        def on_lost() -> None:
            nonlocal lost
            lost = True

        await asyncio.wait_for(
            heartbeat_active_run(redis, CONVERSATION, STREAM, on_lost=on_lost), timeout=2
        )
        redis.set.assert_not_awaited()
        assert lost is True


class TestTheLeaseAbortsWhatItCanNoLongerProtect:
    async def test_a_takeover_aborts_the_block(self) -> None:
        redis = _redis(refresh=0, retake=None)
        reached_the_end = False

        with pytest.raises(ActiveRunLockLost):
            async with active_run_lease(
                redis, CONVERSATION, run_id=RUN, stream_id=STREAM
            ) as acquired:
                assert acquired is True
                await asyncio.sleep(5)
                reached_the_end = True

        assert reached_the_end is False, "the block ran past the loss"

    async def test_the_lock_is_still_released_by_its_owner(self) -> None:
        """The abort must not skip the release: the key is ours until we say so."""
        redis = _redis(refresh=0, retake=None)
        with pytest.raises(ActiveRunLockLost):
            async with active_run_lease(redis, CONVERSATION, run_id=RUN, stream_id=STREAM):
                await asyncio.sleep(5)
        # One EVAL loses the lock, one releases it — the release is conditional
        # on the owner token, so calling it after a takeover frees nothing.
        assert redis.eval.await_count >= 2

    async def test_a_held_lock_lets_the_block_finish(self) -> None:
        redis = _redis(refresh=1)
        done = False
        async with active_run_lease(redis, CONVERSATION, run_id=RUN, stream_id=STREAM) as acquired:
            assert acquired is True
            await asyncio.sleep(0)
            done = True
        assert done is True

    async def test_an_external_cancellation_stays_a_cancellation(self) -> None:
        """Only OUR cancellation is converted; anybody else's must survive."""
        redis = _redis(refresh=1)
        started = asyncio.Event()

        async def body() -> None:
            async with active_run_lease(redis, CONVERSATION, run_id=RUN, stream_id=STREAM):
                started.set()
                await asyncio.sleep(5)

        task = asyncio.create_task(body())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_a_lock_it_never_acquired_is_never_released(self) -> None:
        redis = _redis(refresh=1, acquire=None)
        async with active_run_lease(redis, CONVERSATION, run_id=RUN, stream_id=STREAM) as acquired:
            assert acquired is False
        redis.eval.assert_not_awaited()
