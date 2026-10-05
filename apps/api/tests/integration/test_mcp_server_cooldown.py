"""Real Redis proves expiry and atomic quota sharing between two workers."""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.infrastructure.mcp.rate_limit import MCPServerCooldown

pytestmark = pytest.mark.integration


async def test_two_workers_share_cooldown_without_shortening_it() -> None:
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    key = (uuid4(), uuid4())
    redis_key = MCPServerCooldown._redis_key(key)
    worker_a, worker_b = MCPServerCooldown(), MCPServerCooldown()
    try:
        await redis.ping()
        with patch(
            "src.infrastructure.mcp.rate_limit.get_redis_cache", AsyncMock(return_value=redis)
        ):
            await asyncio.gather(worker_a.record(key, 23), worker_b.record(key, 2))
            ttl = await redis.pttl(redis_key)
            assert 22000 < ttl <= 23000
            assert 22 < await MCPServerCooldown().remaining(key) <= 23
            # Reconnect/reset must not remove the provider's shared refusal.
            worker_a.forget_local(key)
            assert 22 < await worker_a.remaining(key) <= 23
            assert await MCPServerCooldown().remaining((key[0], uuid4())) == 0
            await redis.pexpire(redis_key, 1)
            await asyncio.sleep(0.02)
            assert await MCPServerCooldown().remaining(key) == 0
    finally:
        await redis.delete(redis_key)
        await redis.aclose()
