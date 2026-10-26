"""World tests only use an explicit disposable Redis, never the development cache."""

import os
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from tests.redis_test_url import validated_test_redis_url


@pytest.fixture
async def redis_world() -> AsyncIterator[Redis]:
    url = validated_test_redis_url(os.environ.get("TEST_REDIS_URL"))
    if url is None:
        pytest.fail("World integration tests require an explicit disposable TEST_REDIS_URL")
    redis = Redis.from_url(url, decode_responses=True)
    try:
        await redis.ping()
        yield redis
    finally:
        await redis.aclose()
