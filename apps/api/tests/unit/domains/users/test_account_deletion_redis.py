"""Account deletion purges every user-scoped Redis family (ADR-260).

The conversation reset keeps learning and runtime keys; account deletion is
the one surface that must remove them — and must leave global keys alone.
"""

from __future__ import annotations

import fnmatch
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.users.account_deletion_service import AccountDeletionService

pytestmark = pytest.mark.unit


class _FakeRedis:
    def __init__(self, keys: list[str]) -> None:
        self.data = dict.fromkeys(keys, "1")

    async def scan(self, cursor: int, match: str, count: int) -> tuple[int, list[bytes]]:
        return 0, [k.encode() for k in self.data if fnmatch.fnmatchcase(k, match)]

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                removed += 1
        return removed


async def test_every_user_scoped_family_is_deleted_and_global_keys_survive() -> None:
    uid = uuid.uuid4()
    other = uuid.uuid4()
    user_keys = [
        f"recurrence:{uid}:email",
        f"gmail_history_anchor:{uid}",
        f"adaptive:thr:journal_injection:{uid}",
        f"briefing:v2:lastgood:{uid}:mails",
        f"presence:{uid}:2026-09-03:14",
        f"sse:connection:{uid}",
        f"user:{uid}:sessions",
        f"contacts_list:{uid}",
        f"hitl_pending:{uid}",
        f"apikey:user:{uid}:k1",
        f"apple_rate_limit:calendar:{uid}",
        f"channel:telegram:{uid}",
    ]
    survivors = [
        f"recurrence:{other}:email",
        "llm_cache:_call_router_llm:abc",
        "scheduler:leader",
        f"brand_new_family:{uid}",  # undeclared: never deleted blindly
    ]
    redis = _FakeRedis(user_keys + survivors)

    service = AccountDeletionService(AsyncMock())
    with patch(
        "src.infrastructure.cache.redis.get_redis_cache",
        new=AsyncMock(return_value=redis),
    ):
        await service._cleanup_redis_caches(uid)

    assert set(redis.data) == set(survivors)


async def test_redis_failure_is_best_effort() -> None:
    service = AccountDeletionService(AsyncMock())
    with patch(
        "src.infrastructure.cache.redis.get_redis_cache",
        new=AsyncMock(side_effect=ConnectionError("down")),
    ):
        await service._cleanup_redis_caches(uuid.uuid4())  # must not raise
