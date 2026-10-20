"""SMS admission must fail closed without changing legacy rate-limit policy."""

from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError

from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

pytestmark = pytest.mark.unit


async def test_redis_failure_is_explicit_when_caller_requires_strict_admission() -> None:
    limiter = RedisRateLimiter(AsyncMock())
    limiter._ensure_script_loaded = AsyncMock(side_effect=ConnectionError("unavailable"))
    with pytest.raises(ConnectionError):
        await limiter.acquire("ingestion:source:opaque", 1, 60, fail_open=False)


async def test_existing_callers_keep_their_fail_open_contract() -> None:
    limiter = RedisRateLimiter(AsyncMock())
    limiter._ensure_script_loaded = AsyncMock(side_effect=ConnectionError("unavailable"))
    assert await limiter.acquire("health_metrics_ingest:opaque", 1, 60)
