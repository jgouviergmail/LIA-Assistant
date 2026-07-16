"""Unit tests for the weekly Psyche narrative scheduler job.

Focus: the distributed ``SchedulerLock`` must actually gate execution. The job
enters ``async with SchedulerLock(...) as lock`` and must skip when the lock is
already held by another worker — otherwise every uvicorn worker runs the
dream-cycle concurrently, duplicating LLM cost (audit finding F032).

Regression guard: ``__aenter__`` returns the lock *object* (always truthy), so a
naive ``if not <bound-name>`` never triggers. Only ``lock.acquired`` reflects the
real state — mirroring ``scheduled_action_executor`` and the 12 other jobs.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.scheduler import psyche_snapshot


def _redis_with_set_result(result: object) -> AsyncMock:
    """Build a Redis async mock whose SET NX returns ``result``.

    ``result`` truthy → lock acquired; ``None`` → lock busy (another worker holds it).
    """
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=result)
    return redis


@pytest.mark.asyncio
async def test_skips_when_lock_busy():
    """When SET NX returns None (lock held), the job must skip without generating.

    This is the F032 regression: the skip branch must be reachable. With the
    buggy ``as acquired: if not acquired`` (object, always truthy) the branch is
    dead and ``_generate_narratives`` runs on every worker.
    """
    redis = _redis_with_set_result(None)  # lock busy

    with (
        patch.object(psyche_snapshot.settings, "psyche_enabled", True),
        patch.object(psyche_snapshot, "get_redis_cache", AsyncMock(return_value=redis)),
        patch.object(psyche_snapshot, "_generate_narratives", AsyncMock()) as gen_mock,
    ):
        result = await psyche_snapshot.process_psyche_weekly_narrative()

    assert result == {"skipped": True, "reason": "lock_not_acquired"}
    gen_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_runs_when_lock_acquired():
    """When SET NX succeeds, the job proceeds to narrative generation exactly once."""
    redis = _redis_with_set_result(True)  # lock acquired

    with (
        patch.object(psyche_snapshot.settings, "psyche_enabled", True),
        patch.object(psyche_snapshot, "get_redis_cache", AsyncMock(return_value=redis)),
        patch.object(
            psyche_snapshot,
            "_generate_narratives",
            AsyncMock(return_value={"count": 3, "duration_ms": 12}),
        ) as gen_mock,
    ):
        result = await psyche_snapshot.process_psyche_weekly_narrative()

    assert result == {"count": 3, "duration_ms": 12}
    gen_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_skips_when_psyche_disabled():
    """The feature flag short-circuits before any Redis/lock interaction."""
    with (
        patch.object(psyche_snapshot.settings, "psyche_enabled", False),
        patch.object(psyche_snapshot, "get_redis_cache", AsyncMock()) as redis_mock,
        patch.object(psyche_snapshot, "_generate_narratives", AsyncMock()) as gen_mock,
    ):
        result = await psyche_snapshot.process_psyche_weekly_narrative()

    assert result == {"skipped": True, "reason": "psyche disabled"}
    redis_mock.assert_not_awaited()
    gen_mock.assert_not_awaited()
