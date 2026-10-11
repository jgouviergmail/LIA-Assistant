"""A stale or corrupt owner index must neither expose nor revoke another account's session."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.infrastructure.cache.session_store import (
    SessionListingObservation,
    SessionStore,
    UserSession,
)

pytestmark = pytest.mark.unit


async def test_bounded_native_read_refuses_large_index_before_fetching_payloads() -> None:
    from src.infrastructure.cache.session_store import SessionListingLimitError

    redis = AsyncMock()
    redis.scard.return_value = 3
    with pytest.raises(SessionListingLimitError):
        await SessionStore(redis).list_user_sessions("one", max_sessions=2)
    redis.smembers.assert_not_awaited()


async def test_bounded_native_read_rechecks_growth_between_count_and_members() -> None:
    from src.infrastructure.cache.session_store import SessionListingLimitError

    redis = fleet(["null", "null", "null"])
    redis.scard.return_value = 2
    with pytest.raises(SessionListingLimitError):
        await SessionStore(redis).list_user_sessions("one", max_sessions=2)
    redis.pipeline.assert_not_called()


def fleet(payloads: list[str | None]) -> AsyncMock:
    redis = AsyncMock()
    saved = {f"session-{index}": payload for index, payload in enumerate(payloads)}
    redis.smembers.return_value = set(saved)

    def make_pipeline() -> MagicMock:
        pipeline = MagicMock()
        keys: list[str] = []
        pipeline.get.side_effect = lambda key: keys.append(key.split(":", 1)[1])
        pipeline.execute = AsyncMock(side_effect=lambda: [saved[key] for key in keys])
        return pipeline

    redis.pipeline = MagicMock(side_effect=make_pipeline)
    return redis


async def test_foreign_session_in_owner_index_is_not_read_or_revoked() -> None:
    owner = str(uuid4())
    other = UserSession(session_id="foreign-cookie", user_id=str(uuid4()))
    redis = fleet([json.dumps(other.to_dict())])
    store = SessionStore(redis)
    assert await store.list_user_sessions(owner) == []
    assert await store.delete_session_by_display_id(owner, other.display_id) is False
    redis.delete.assert_not_awaited()


@pytest.mark.parametrize("payload", ["", "[]", "null", '{"user_id":"one","created_at":"bad"}'])
async def test_invalid_index_metadata_is_explicitly_incomplete(payload: str) -> None:
    observation = SessionListingObservation()
    result = await SessionStore(fleet([payload])).list_user_sessions("one", observation=observation)
    assert result == [] and observation.incomplete is True


async def test_expired_index_entry_is_normal_absence_without_incomplete_claim() -> None:
    observation = SessionListingObservation()
    result = await SessionStore(fleet([None])).list_user_sessions("one", observation=observation)
    assert result == [] and observation.incomplete is False


@pytest.mark.parametrize(
    "payload",
    ["[]", "null", '{"user_id":"one","created_at":"bad"}', '{"user_id":"one","created_at":4}'],
)
async def test_malformed_session_metadata_does_not_break_device_listing(payload: str) -> None:
    assert await SessionStore(fleet([payload])).list_user_sessions("one") == []


async def test_naive_legacy_dates_are_normalized_without_breaking_mixed_session_sorting() -> None:
    older = UserSession(session_id="older", user_id="one", created_at=datetime(2020, 1, 1))
    newer = UserSession(session_id="newer", user_id="one", created_at=datetime.now(UTC))
    redis = fleet([json.dumps(older.to_dict()), json.dumps(newer.to_dict())])
    sessions = await SessionStore(redis).list_user_sessions("one")
    assert [session.session_id for session in sessions] == ["session-1", "session-0"]
    assert all(session.created_at.tzinfo is not None for session in sessions)
