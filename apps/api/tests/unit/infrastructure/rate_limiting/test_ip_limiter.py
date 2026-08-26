"""
The per-IP rate limit dependency, now that it is shared.

It used to live in the auth domain, which is why four unrelated domains import
their limiters from ``domains/auth/dependencies``. The behaviour must not change
as it moves: the Redis keys it writes are the same keys, so a deployment
upgrading mid-window keeps counting rather than handing every caller a fresh
budget. That continuity is the first thing asserted here.

Fail-open is deliberate and pinned too: Redis being down must not lock everyone
out of signing in.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.core.exceptions import RateLimitError
from src.infrastructure.rate_limiting.ip_limiter import create_ip_rate_limiter

pytestmark = pytest.mark.unit


def _request(ip: str = "203.0.113.7") -> Mock:
    request = Mock()
    request.client = Mock(host=ip)
    request.headers = {}
    return request


def _limiter(*, allowed: bool) -> Mock:
    limiter = Mock()
    limiter.acquire = AsyncMock(return_value=allowed)
    return limiter


class TestKeying:
    async def test_the_key_is_namespace_action_and_ip(self) -> None:
        limiter = _limiter(allowed=True)
        dependency = create_ip_rate_limiter(namespace="push_relay", action="register", max_calls=5)

        with patch(
            "src.infrastructure.rate_limiting.ip_limiter.get_rate_limiter",
            new=AsyncMock(return_value=limiter),
        ):
            await dependency(_request("198.51.100.9"))

        assert limiter.acquire.await_args.kwargs["key"] == "push_relay:register:198.51.100.9"

    async def test_the_auth_namespace_is_byte_for_byte_what_it_was(self) -> None:
        limiter = _limiter(allowed=True)
        dependency = create_ip_rate_limiter(namespace="auth", action="login", max_calls=10)

        with patch(
            "src.infrastructure.rate_limiting.ip_limiter.get_rate_limiter",
            new=AsyncMock(return_value=limiter),
        ):
            await dependency(_request("203.0.113.7"))

        # Changing this string silently resets every live window in production.
        assert limiter.acquire.await_args.kwargs["key"] == "auth:login:203.0.113.7"


class TestVerdict:
    async def test_a_call_within_the_window_passes(self) -> None:
        dependency = create_ip_rate_limiter(namespace="auth", action="login", max_calls=10)

        with patch(
            "src.infrastructure.rate_limiting.ip_limiter.get_rate_limiter",
            new=AsyncMock(return_value=_limiter(allowed=True)),
        ):
            assert await dependency(_request()) is None

    async def test_exceeding_the_window_raises_a_typed_429(self) -> None:
        dependency = create_ip_rate_limiter(
            namespace="auth", action="login", max_calls=3, window_seconds=60
        )

        with patch(
            "src.infrastructure.rate_limiting.ip_limiter.get_rate_limiter",
            new=AsyncMock(return_value=_limiter(allowed=False)),
        ):
            with pytest.raises(RateLimitError) as exc_info:
                await dependency(_request())

        exc = exc_info.value
        assert exc.status_code == 429
        assert exc.headers == {"Retry-After": "60"}
        assert exc.detail["retry_after_seconds"] == 60

    async def test_redis_being_unreachable_lets_the_caller_through(self) -> None:
        dependency = create_ip_rate_limiter(namespace="auth", action="login", max_calls=3)

        with patch(
            "src.infrastructure.rate_limiting.ip_limiter.get_rate_limiter",
            new=AsyncMock(side_effect=ConnectionError("redis down")),
        ):
            # Fail-open: a cache outage must not become an outage of signing in.
            assert await dependency(_request()) is None
