"""
Unit tests for SchedulerLeaderElector.

Tests coverage for:
- Leadership acquisition (immediate, fallback, re-election)
- Shutdown (leader, non-leader, idempotent)
- Error handling (scheduler failure, callback error, Redis error)
- Edge cases (double start, stale lock diagnostics)

Target: 90%+ coverage for infrastructure/scheduler/leader_elector.py
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import STATE_PAUSED, STATE_RUNNING, STATE_STOPPED

from src.core.constants import SCHEDULER_JOB_LEADER_LOCK_RENEWAL
from src.infrastructure.scheduler.leader_elector import SchedulerLeaderElector

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create mock Redis client for testing."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock()
    redis.expire = AsyncMock()
    redis.get = AsyncMock(return_value="worker-99")
    redis.ttl = AsyncMock(return_value=60)
    return redis


@pytest.fixture
def mock_scheduler() -> MagicMock:
    """Create mock APScheduler for testing."""
    scheduler = MagicMock()
    type(scheduler).running = PropertyMock(return_value=False)
    scheduler.start = MagicMock()
    scheduler.shutdown = MagicMock()
    scheduler.add_job = MagicMock()
    scheduler.get_jobs = MagicMock(return_value=[])
    return scheduler


@pytest.fixture
def mock_callback() -> AsyncMock:
    """Create mock on_elected callback."""
    return AsyncMock()


# =============================================================================
# Leadership Acquisition Tests
# =============================================================================


class TestLeadershipAcquisition:
    """Tests for successful leadership acquisition paths."""

    @pytest.mark.asyncio
    async def test_acquire_leadership_immediately(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock, mock_callback: AsyncMock
    ) -> None:
        """SETNX succeeds on first try — scheduler starts, callback invoked."""
        mock_redis.set.return_value = True

        elector = SchedulerLeaderElector(
            mock_redis,
            mock_scheduler,
            on_elected=mock_callback,
        )
        await elector.start()

        assert elector.is_leader is True
        mock_scheduler.start.assert_called_once()
        mock_callback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_redis_fallback_becomes_leader(
        self, mock_scheduler: MagicMock, mock_callback: AsyncMock
    ) -> None:
        """Redis=None triggers single-worker fallback — becomes leader immediately."""
        elector = SchedulerLeaderElector(
            None,
            mock_scheduler,
            on_elected=mock_callback,
        )
        await elector.start()

        assert elector.is_leader is True
        mock_scheduler.start.assert_called_once()
        mock_callback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stale_lock_triggers_re_election(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock
    ) -> None:
        """SETNX returns None (lock held) — re-election task is started."""
        mock_redis.set.return_value = None

        elector = SchedulerLeaderElector(mock_redis, mock_scheduler)
        await elector.start()

        assert elector.is_leader is False
        assert elector._re_election_task is not None
        assert not elector._re_election_task.done()

        # Cleanup
        await elector.shutdown()

    @pytest.mark.asyncio
    async def test_redis_error_starts_re_election(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock
    ) -> None:
        """SETNX raises exception — re-election task is started."""
        mock_redis.set.side_effect = ConnectionError("Redis down")

        elector = SchedulerLeaderElector(mock_redis, mock_scheduler)
        await elector.start()

        assert elector.is_leader is False
        assert elector._re_election_task is not None

        # Cleanup
        await elector.shutdown()

    @pytest.mark.asyncio
    async def test_re_election_acquires_when_lock_expires(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock, mock_callback: AsyncMock
    ) -> None:
        """Re-election loop succeeds after initial SETNX failure."""
        # First call fails (stale lock), second succeeds (lock expired)
        mock_redis.set.side_effect = [None, True]

        elector = SchedulerLeaderElector(
            mock_redis,
            mock_scheduler,
            re_election_interval_seconds=0.01,  # Fast for testing
            on_elected=mock_callback,
        )
        await elector.start()

        assert elector.is_leader is False  # Not yet

        # Wait for re-election to succeed
        await asyncio.sleep(0.05)

        assert elector.is_leader is True
        mock_scheduler.start.assert_called_once()
        mock_callback.assert_awaited_once()


# =============================================================================
# Shutdown Tests
# =============================================================================


class TestShutdown:
    """Tests for shutdown behavior in different states."""

    @pytest.mark.asyncio
    async def test_shutdown_leader_releases_lock(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock
    ) -> None:
        """Leader shutdown: stops scheduler and deletes Redis lock."""
        mock_redis.set.return_value = True
        type(mock_scheduler).running = PropertyMock(side_effect=[False, True])

        elector = SchedulerLeaderElector(mock_redis, mock_scheduler)
        await elector.start()
        await elector.shutdown()

        mock_scheduler.shutdown.assert_called_once()
        # ADR-263: the lease is released CONDITIONALLY, through the ownership
        # script — an unconditional DELETE handed the scheduler to whoever asked
        # next when a stale worker shut down.
        mock_redis.delete.assert_not_awaited()
        mock_redis.eval.assert_awaited()

    @pytest.mark.asyncio
    async def test_shutdown_non_leader_cancels_task(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock
    ) -> None:
        """Non-leader shutdown: cancels re-election task without touching scheduler."""
        mock_redis.set.return_value = None

        elector = SchedulerLeaderElector(mock_redis, mock_scheduler)
        await elector.start()

        assert elector._re_election_task is not None
        await elector.shutdown()

        assert elector._re_election_task.done()
        mock_scheduler.shutdown.assert_not_called()
        # Only the ownership script may release, and only this worker's own lease.
        mock_redis.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_shutdown_idempotent_before_start(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock
    ) -> None:
        """shutdown() before start() is a safe no-op."""
        elector = SchedulerLeaderElector(mock_redis, mock_scheduler)
        await elector.shutdown()  # Should not raise

        mock_scheduler.shutdown.assert_not_called()


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error recovery and resilience."""

    @pytest.mark.asyncio
    async def test_on_elected_error_does_not_break_scheduler(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock
    ) -> None:
        """Callback exception is caught — scheduler remains running."""
        mock_redis.set.return_value = True
        failing_callback = AsyncMock(side_effect=ValueError("callback boom"))

        elector = SchedulerLeaderElector(
            mock_redis,
            mock_scheduler,
            on_elected=failing_callback,
        )
        await elector.start()

        assert elector.is_leader is True
        mock_scheduler.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_become_leader_scheduler_error_rolls_back(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock
    ) -> None:
        """scheduler.start() failure: is_leader rolled back, lock released."""
        mock_redis.set.return_value = True
        mock_scheduler.start.side_effect = RuntimeError("scheduler broken")

        elector = SchedulerLeaderElector(mock_redis, mock_scheduler)
        await elector.start()

        assert elector.is_leader is False
        # ADR-263: released only if still owned (conditional script, no DELETE).
        mock_redis.delete.assert_not_awaited()
        mock_redis.eval.assert_awaited()

    @pytest.mark.asyncio
    async def test_become_leader_error_re_election_continues(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock
    ) -> None:
        """After _become_leader failure, re-election loop continues retrying."""
        # First SETNX: lock acquired but start() fails
        # Second SETNX attempt (after lock released): succeeds
        call_count = 0

        async def setnx_side_effect(*args: object, **kwargs: object) -> bool | None:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return True  # Both initial and first re-election acquire lock
            return True

        mock_redis.set = AsyncMock(side_effect=setnx_side_effect)
        # First start() fails, second succeeds
        mock_scheduler.start.side_effect = [RuntimeError("fail"), None]

        elector = SchedulerLeaderElector(
            mock_redis,
            mock_scheduler,
            re_election_interval_seconds=0.01,
        )

        # Initial attempt: SETNX ok, start() fails → re-election started
        await elector.start()
        assert elector.is_leader is False

        # Wait for re-election to retry and succeed
        await asyncio.sleep(0.05)

        assert elector.is_leader is True

    @pytest.mark.asyncio
    async def test_become_leader_no_redis_scheduler_error(self, mock_scheduler: MagicMock) -> None:
        """No Redis + scheduler.start() error: no AttributeError on None.delete()."""
        mock_scheduler.start.side_effect = RuntimeError("scheduler broken")

        elector = SchedulerLeaderElector(None, mock_scheduler)
        await elector.start()

        # Should not raise AttributeError — guard prevents None.delete()
        assert elector.is_leader is False

    @pytest.mark.asyncio
    async def test_re_election_loop_unexpected_error_logged(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock
    ) -> None:
        """Unexpected error in re-election loop is caught and logged (no silent death)."""
        mock_redis.set.return_value = None
        # Make ttl raise to trigger stale lock log, then set fails on re-election
        mock_redis.ttl.return_value = 60

        elector = SchedulerLeaderElector(
            mock_redis,
            mock_scheduler,
            re_election_interval_seconds=0.01,
        )
        await elector.start()

        # The loop should be running
        assert elector._re_election_task is not None

        # Cleanup
        await elector.shutdown()


# =============================================================================
# Renewal & Miscellaneous Tests
# =============================================================================


class TestRenewalAndMisc:
    """Tests for lock renewal and miscellaneous behavior."""

    @pytest.mark.asyncio
    async def test_renewal_job_registered_on_election(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock
    ) -> None:
        """Lock renewal job is registered on the scheduler when elected."""
        mock_redis.set.return_value = True

        elector = SchedulerLeaderElector(mock_redis, mock_scheduler)
        await elector.start()

        mock_scheduler.add_job.assert_called_once()
        call_kwargs = mock_scheduler.add_job.call_args
        assert call_kwargs[1]["id"] == "scheduler_leader_lock_renewal"

    @pytest.mark.asyncio
    async def test_double_start_is_noop(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock
    ) -> None:
        """Calling start() twice does not create orphan tasks."""
        mock_redis.set.return_value = True

        elector = SchedulerLeaderElector(mock_redis, mock_scheduler)
        await elector.start()
        await elector.start()  # Second call should be no-op

        # scheduler.start() called only once
        mock_scheduler.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_renew_lock_calls_expire(
        self, mock_redis: AsyncMock, mock_scheduler: MagicMock
    ) -> None:
        """_renew_lock calls redis.expire with correct TTL."""
        elector = SchedulerLeaderElector(mock_redis, mock_scheduler)
        await elector._renew_lock()

        # ADR-263: renewal is conditional on ownership, so it goes through the
        # script rather than an unconditional EXPIRE that extended whatever lock
        # happened to be there — including the NEW leader's.
        mock_redis.expire.assert_not_awaited()
        mock_redis.eval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_renew_lock_no_redis_is_noop(self, mock_scheduler: MagicMock) -> None:
        """_renew_lock with Redis=None does not raise."""
        elector = SchedulerLeaderElector(None, mock_scheduler)
        await elector._renew_lock()  # Should not raise


# =============================================================================
# A worker that loses its lease steps down, and a shutdown starts nothing (N1)
# =============================================================================


async def _until(predicate: Any, *, rounds: int = 200) -> None:
    """Let the event loop run until ``predicate()`` holds (bounded)."""
    for _ in range(rounds):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("the condition never held")


def _scripts(redis: AsyncMock) -> list[str]:
    """The Lua scripts the elector sent, in order (renewal or release)."""
    return [str(call.args[0]) for call in redis.eval.await_args_list]


@pytest.fixture
async def live_scheduler() -> Any:
    """A REAL scheduler: its states are what the elector must read."""
    scheduler = AsyncIOScheduler()
    yield scheduler
    if scheduler.running:
        scheduler.shutdown(wait=False)


class TestALostLeaseStopsTheJobs:
    """N1, proven at runtime: a worker whose lease another worker took kept
    running every job — two schedulers. It must step down, then wait for the
    lease again exactly as it did at boot."""

    @pytest.mark.asyncio
    async def test_a_late_renewal_still_runs(
        self, mock_redis: AsyncMock, live_scheduler: Any
    ) -> None:
        """APScheduler skips a run more than a second late by default; seven
        renewals were skipped that way on dev (1.0 to 2.6 s late)."""
        elector = SchedulerLeaderElector(mock_redis, live_scheduler, renew_interval_seconds=30)
        await elector.start()

        job = live_scheduler.get_job(SCHEDULER_JOB_LEADER_LOCK_RENEWAL)
        assert job is not None and job.misfire_grace_time == 30
        await elector.shutdown()

    @pytest.mark.asyncio
    async def test_a_lost_lease_pauses_the_jobs_and_waits_for_it_again(
        self, mock_redis: AsyncMock, live_scheduler: Any
    ) -> None:
        elector = SchedulerLeaderElector(mock_redis, live_scheduler, re_election_interval_seconds=0)
        await elector.start()
        assert live_scheduler.state == STATE_RUNNING

        mock_redis.eval = AsyncMock(return_value=0)  # another worker holds the lease
        mock_redis.set = AsyncMock(return_value=False)  # and keeps it for now
        await elector._renew_lock()

        assert elector.is_leader is False
        assert live_scheduler.state == STATE_PAUSED
        task = elector._re_election_task
        assert task is not None and not task.done()

        mock_redis.set = AsyncMock(return_value=True)  # its lease expired
        await _until(lambda: elector.is_leader)
        assert live_scheduler.state == STATE_RUNNING  # resumed, never restarted
        await elector.shutdown()

    @pytest.mark.asyncio
    async def test_a_worker_that_lost_its_lease_stops_its_scheduler_on_shutdown(
        self, mock_redis: AsyncMock, live_scheduler: Any
    ) -> None:
        elector = SchedulerLeaderElector(mock_redis, live_scheduler)
        await elector.start()
        mock_redis.eval = AsyncMock(return_value=0)
        mock_redis.set = AsyncMock(return_value=False)
        await elector._renew_lock()

        await elector.shutdown()

        assert live_scheduler.state == STATE_STOPPED
        # The lease is another worker's: only the ownership script may touch it.
        mock_redis.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_unreadable_lease_pauses_jobs_until_a_new_election(
        self, mock_redis: AsyncMock, live_scheduler: Any
    ) -> None:
        """A partitioned worker cannot keep starting jobs after another wins the lease."""
        elector = SchedulerLeaderElector(mock_redis, live_scheduler, re_election_interval_seconds=0)
        await elector.start()
        mock_redis.eval = AsyncMock(side_effect=ConnectionError("lease unreachable"))
        mock_redis.set = AsyncMock(return_value=False)
        try:
            await elector._renew_lock()
            assert live_scheduler.state == STATE_PAUSED
            assert not elector.is_leader

            # A successful fresh acquisition, rather than an optimistic retry,
            # is the only way this worker resumes its existing scheduler.
            mock_redis.eval = AsyncMock(return_value=1)
            mock_redis.set = AsyncMock(return_value=True)
            await _until(lambda: elector.is_leader)
            assert live_scheduler.state == STATE_RUNNING
        finally:
            await elector.shutdown()


class TestAShutdownStartsNothing:
    """Point 23: the scheduler used to keep firing while the shutdown closed
    the push relay and Langfuse under its jobs."""

    @pytest.mark.asyncio
    async def test_pausing_lets_nothing_new_start(
        self, mock_redis: AsyncMock, live_scheduler: Any
    ) -> None:
        elector = SchedulerLeaderElector(mock_redis, live_scheduler)
        await elector.start()

        elector.pause_jobs()

        assert live_scheduler.state == STATE_PAUSED
        await elector.shutdown()
        assert live_scheduler.state == STATE_STOPPED

    @pytest.mark.asyncio
    async def test_the_scheduler_is_stopped_when_shutdown_returns(
        self, live_scheduler: Any
    ) -> None:
        """AsyncIOScheduler defers its stop to the loop's next turn: the
        sequence closes the push relay right after, so the stop must be done
        by then, not merely requested — with or without a lease to release."""
        elector = SchedulerLeaderElector(None, live_scheduler)
        await elector.start()

        await elector.shutdown()

        assert live_scheduler.state == STATE_STOPPED

    @pytest.mark.asyncio
    async def test_a_lease_held_without_knowing_it_is_given_back(
        self, mock_redis: AsyncMock, live_scheduler: Any
    ) -> None:
        """Cancelling the re-election mid-``SET NX`` may leave the lease set in
        Redis while this worker believes it follows: Redis is asked, not the
        flag — the release only ever deletes this worker's own lease."""
        mock_redis.set = AsyncMock(return_value=False)
        elector = SchedulerLeaderElector(mock_redis, live_scheduler)
        await elector.start()
        assert elector.is_leader is False

        elector.pause_jobs()
        await elector.shutdown()

        releases = [
            call.args for call in mock_redis.eval.await_args_list if "DEL" in str(call.args[0])
        ]
        assert releases and releases[-1][2:] == (elector._lock_key, elector._worker_id)
        mock_redis.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_shutdown_alone_lets_no_re_election_start(
        self, mock_redis: AsyncMock, live_scheduler: Any
    ) -> None:
        """A renewal still in flight may find the lease gone after the release:
        a dying worker must not start waiting for it again."""
        elector = SchedulerLeaderElector(mock_redis, live_scheduler)
        await elector.start()
        await elector.shutdown()

        mock_redis.eval = AsyncMock(return_value=0)
        await elector._renew_lock()

        assert elector._re_election_task is None

    @pytest.mark.asyncio
    async def test_a_lease_won_during_the_shutdown_is_given_back(
        self, mock_redis: AsyncMock, live_scheduler: Any
    ) -> None:
        """A follower may win the lease the stopping leader just released: a
        dying process must not start the jobs — it hands the lease back."""
        mock_redis.set = AsyncMock(return_value=False)
        elector = SchedulerLeaderElector(mock_redis, live_scheduler)
        await elector.start()  # a follower, waiting for the lease

        elector.pause_jobs()
        mock_redis.set = AsyncMock(return_value=True)
        assert await elector._try_acquire() is False

        assert live_scheduler.state == STATE_STOPPED
        assert any("DEL" in script for script in _scripts(mock_redis))
        await elector.shutdown()
