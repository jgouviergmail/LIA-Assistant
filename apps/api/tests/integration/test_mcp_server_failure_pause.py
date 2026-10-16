"""Real Redis proves the failure pause doubles, caps, is shared and clears (point 29)."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.infrastructure.mcp.rate_limit import MCPServerFailures

pytestmark = pytest.mark.integration


async def test_the_pause_doubles_to_its_cap_is_shared_and_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mcp_user_failure_pause_base_seconds", 2)
    monkeypatch.setattr(settings, "mcp_user_failure_pause_max_seconds", 5)
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    key = (uuid4(), uuid4())
    worker_a, worker_b = MCPServerFailures(), MCPServerFailures()
    try:
        await redis.ping()
        with patch(
            "src.infrastructure.mcp.rate_limit.get_redis_cache", AsyncMock(return_value=redis)
        ):
            assert await worker_a.record(key) == 2
            # Another worker sees the same pause.
            assert 1.5 < await worker_b.remaining(key) <= 2
            assert await worker_b.record(key) == 4
            assert await worker_a.record(key) == 5  # capped
            # A success clears both the pause and the count.
            await worker_b.clear(key)
            assert await worker_a.remaining(key) == 0
            assert await worker_a.record(key) == 2
            # Another server of the same account is untouched.
            assert await worker_a.remaining((key[0], uuid4())) == 0
    finally:
        await redis.delete(MCPServerFailures._count_key(key), MCPServerFailures._pause_key(key))
        await redis.aclose()
