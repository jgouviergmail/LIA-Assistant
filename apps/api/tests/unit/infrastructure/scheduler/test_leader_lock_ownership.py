"""A lease is renewed and released by its OWNER, never unconditionally (ADR-263).

The systemic rule is explicit: ``SET NX`` followed by an unconditional
``EXPIRE``/``DELETE`` is forbidden. The leader election broke it in both
directions:

- ``EXPIRE`` extended whatever lock was there, so a worker that had already
  lost leadership kept renewing the NEW leader's lease — indefinitely;
- ``DELETE`` removed it outright, so a stale worker's shutdown handed the whole
  scheduler to whoever asked next, mid-term.

The active-run lock in ``run_stream_broker`` already does this correctly with
two small Lua scripts; the same shape is used here, so there is one idea of
what owning a lease means.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.scheduler.leader_elector import SchedulerLeaderElector

pytestmark = [pytest.mark.unit]


@pytest.fixture
def redis() -> AsyncMock:
    client = AsyncMock()
    client.set = AsyncMock(return_value=True)
    client.eval = AsyncMock(return_value=1)
    client.delete = AsyncMock()
    client.expire = AsyncMock()
    return client


@pytest.fixture
def elector(redis: AsyncMock) -> SchedulerLeaderElector:
    instance = SchedulerLeaderElector(
        redis=redis, scheduler=MagicMock(), lock_key="lia:scheduler:leader"
    )
    return instance


class TestRenewal:
    async def test_it_renews_conditionally_on_ownership(
        self, elector: SchedulerLeaderElector, redis: AsyncMock
    ) -> None:
        await elector._renew_lock()

        redis.expire.assert_not_called()
        redis.eval.assert_awaited()
        # redis-py: eval(script, numkeys, *keys, *args)
        script, numkeys, lock_key, worker_id, ttl = redis.eval.await_args.args
        assert "GET" in script and "EXPIRE" in script
        assert numkeys == 1
        assert lock_key == "lia:scheduler:leader"
        assert worker_id == elector._worker_id
        assert int(ttl) > 0

    async def test_losing_the_lease_stops_the_renewal(
        self, elector: SchedulerLeaderElector, redis: AsyncMock
    ) -> None:
        """A worker that no longer owns it must not extend the new leader's term."""
        elector._is_leader = True
        redis.eval = AsyncMock(return_value=0)

        await elector._renew_lock()

        assert elector._is_leader is False


class TestRelease:
    async def test_it_releases_conditionally_on_ownership(
        self, elector: SchedulerLeaderElector, redis: AsyncMock
    ) -> None:
        await elector._release_lock()

        redis.delete.assert_not_called()
        script, numkeys, lock_key, worker_id = redis.eval.await_args.args
        assert "DEL" in script
        assert numkeys == 1
        assert lock_key == "lia:scheduler:leader"
        assert worker_id == elector._worker_id

    async def test_a_stale_worker_releases_nothing(
        self, elector: SchedulerLeaderElector, redis: AsyncMock
    ) -> None:
        redis.eval = AsyncMock(return_value=0)
        await elector._release_lock()
        redis.delete.assert_not_called()
