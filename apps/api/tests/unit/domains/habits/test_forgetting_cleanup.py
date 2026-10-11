"""An advisory failure must neither invent success nor skip the other owned cleanup."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.habits.forgetting import clear_habit_advisory_state

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failed", ["ledger", "presence", "redis", "none"])
async def test_advisory_cleanup_attempts_each_owned_scope_and_reports_failure(
    monkeypatch: pytest.MonkeyPatch, failed: str
) -> None:
    owner, redis = uuid4(), object()
    get = AsyncMock(return_value=redis)
    ledger, presence = AsyncMock(return_value=3), AsyncMock(return_value=2)
    if failed == "redis":
        get.side_effect = ConnectionError("down")
    elif failed == "ledger":
        ledger.side_effect = ConnectionError("down")
    elif failed == "presence":
        presence.side_effect = TimeoutError("late")
    monkeypatch.setattr("src.infrastructure.cache.redis.get_redis_cache", get)
    monkeypatch.setattr("src.infrastructure.cache.recurrence_store.delete_user_ledger", ledger)
    monkeypatch.setattr("src.domains.habits.presence.forget_user", presence)
    assert await clear_habit_advisory_state(owner) is (failed == "none")
    if failed == "redis":
        ledger.assert_not_awaited()
        presence.assert_not_awaited()
    else:
        ledger.assert_awaited_once_with(redis, str(owner))
        presence.assert_awaited_once_with(redis, str(owner))
