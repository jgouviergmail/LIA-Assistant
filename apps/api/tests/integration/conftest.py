"""
Integration-test fixtures (scoped to tests/integration/ only).

These fixtures complement the global tests/conftest.py without taxing the
unit-test runs (pre-commit) with per-test Redis round trips.
"""

import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def _purge_auth_rate_limit_keys():
    """Purge auth rate-limit buckets before each integration test.

    The auth endpoints are rate limited per client IP (e.g. 10 logins/min,
    see src/domains/auth/dependencies.py) and the counters live in Redis,
    NOT in the test database. Integration tests log in through the real
    HTTP flow (``authenticated_client`` / ``admin_client``), all from the
    same test-client IP, so a full run trips the limiter after a handful
    of tests and every later login fails with 429.

    Deleting the ``auth:*`` buckets through the limiter's own Redis client
    (which targets the cache Redis, whatever DB index it is configured on)
    restores the production semantics of "a fresh client" per test. No-op
    when Redis is unavailable — tests that need Redis fail on their own.
    """
    try:
        from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

        limiter = await get_rate_limiter()
        keys = [key async for key in limiter.redis.scan_iter(match="auth:*")]
        if keys:
            await limiter.redis.delete(*keys)
    except Exception:  # noqa: BLE001 — Redis down: let the tests surface it
        pass
    yield
