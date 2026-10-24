"""A sliding-window limiter with ``RedisRateLimiter.acquire``'s contract (ADR-363).

The real limiter runs a Lua script on Redis; its atomicity is proven by the
integration suite on a real Redis. Unit tests need only its contract: an
attempt is recorded when, and only when, it is admitted.
"""

import pytest

from src.core.config import settings


class SlidingWindowLimiter:
    """In-memory stand-in for ``RedisRateLimiter`` with a clock the test moves."""

    def __init__(self) -> None:
        self.now = 1_000_000.0
        self.entries: dict[str, list[float]] = {}

    async def acquire(
        self, key: str, max_calls: int, window_seconds: int, *, fail_open: bool = True
    ) -> bool:
        live = [t for t in self.entries.get(key, []) if t > self.now - window_seconds]
        admitted = len(live) < max_calls
        if admitted:
            live.append(self.now)
        self.entries[key] = live
        return admitted


def install_reset_budget(monkeypatch: pytest.MonkeyPatch) -> SlidingWindowLimiter:
    """Route the reset budget to a fresh in-memory limiter, at the default limits."""
    fake = SlidingWindowLimiter()

    async def _get() -> SlidingWindowLimiter:
        return fake

    monkeypatch.setattr("src.domains.auth.password_reset_policy.get_rate_limiter", _get)
    monkeypatch.setattr(settings, "password_reset_account_interval_seconds", 900)
    monkeypatch.setattr(settings, "password_reset_account_daily_max", 3)
    return fake
