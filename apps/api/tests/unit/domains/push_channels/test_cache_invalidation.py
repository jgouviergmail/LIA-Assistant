"""Per-provider cache invalidation on push notification (lot H, 2026-08).

A notification means the source changed: the matching briefing section cache
is dropped so the next briefing read refetches, and Gmail search caches are
purged (their content may include the new/changed messages).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.push_channels.cache_invalidation import invalidate_for_provider
from src.domains.push_channels.models import PushChannelProvider

pytestmark = pytest.mark.unit


def _redis(scan_keys: list[str] | None = None) -> MagicMock:
    redis = MagicMock()
    redis.delete = AsyncMock(return_value=1)

    async def _scan_iter(match: str) -> Any:
        for key in scan_keys or []:
            yield key

    redis.scan_iter = _scan_iter
    return redis


class TestInvalidateForProvider:
    async def test_calendar_drops_the_briefing_agenda_section(self) -> None:
        user_id = uuid4()
        redis = _redis()
        with patch(
            "src.domains.push_channels.cache_invalidation.get_redis_cache",
            new=AsyncMock(return_value=redis),
        ):
            await invalidate_for_provider(PushChannelProvider.GOOGLE_CALENDAR.value, user_id)
        deleted = {call.args[0] for call in redis.delete.await_args_list}
        assert f"briefing:v2:{user_id}:agenda" in deleted

    async def test_drive_drops_the_briefing_documents_section(self) -> None:
        user_id = uuid4()
        redis = _redis()
        with patch(
            "src.domains.push_channels.cache_invalidation.get_redis_cache",
            new=AsyncMock(return_value=redis),
        ):
            await invalidate_for_provider(PushChannelProvider.GOOGLE_DRIVE.value, user_id)
        deleted = {call.args[0] for call in redis.delete.await_args_list}
        assert f"briefing:v2:{user_id}:documents" in deleted

    async def test_gmail_drops_mails_section_and_purges_search_caches(self) -> None:
        user_id = uuid4()
        stale = [f"gmail:search:{user_id}:abc:10", f"gmail:search:{user_id}:def:5"]
        redis = _redis(scan_keys=stale)
        with patch(
            "src.domains.push_channels.cache_invalidation.get_redis_cache",
            new=AsyncMock(return_value=redis),
        ):
            await invalidate_for_provider(PushChannelProvider.GOOGLE_GMAIL.value, user_id)
        deleted_single = {call.args[0] for call in redis.delete.await_args_list}
        assert f"briefing:v2:{user_id}:mails" in deleted_single
        # The two stale search keys are deleted (batched *args call).
        all_deleted_args = [arg for call in redis.delete.await_args_list for arg in call.args]
        assert set(stale) <= set(all_deleted_args)

    async def test_redis_failure_is_best_effort(self) -> None:
        # Invalidation must never break the webhook path — a failed Redis is
        # a missed optimization (TTL still bounds staleness), not an error.
        with patch(
            "src.domains.push_channels.cache_invalidation.get_redis_cache",
            new=AsyncMock(side_effect=ConnectionError("down")),
        ):
            await invalidate_for_provider(PushChannelProvider.GOOGLE_CALENDAR.value, uuid4())


class TestCalendarDepartureInvalidation:
    """ADR-261 (P3): a changed agenda makes the cached departure advice stale."""

    async def test_calendar_notification_drops_the_departure_advice(self) -> None:
        from uuid import uuid4

        from src.domains.push_channels.cache_invalidation import invalidate_for_provider
        from src.domains.push_channels.models import PushChannelProvider

        user_id = uuid4()
        redis = _redis(scan_keys=[f"heartbeat:departure:{user_id}:abc"])
        with patch(
            "src.domains.push_channels.cache_invalidation.get_redis_cache",
            new=AsyncMock(return_value=redis),
        ):
            await invalidate_for_provider(PushChannelProvider.GOOGLE_CALENDAR.value, user_id)
        deleted = [call.args for call in redis.delete.await_args_list]
        assert any(f"heartbeat:departure:{user_id}:abc" in args for args in deleted)
