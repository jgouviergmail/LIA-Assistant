"""The owner-token claim primitive (ADR-298, extracted from shared_flight).

One implementation of "SET NX with a token, compare-and-delete to release"
for every caller that must never delete a claim it no longer owns.
"""

from __future__ import annotations

import asyncio
from collections import Counter

import pytest

from src.infrastructure.locks.redis_claim import acquire_claim, release_claim, try_claim

pytestmark = pytest.mark.unit


class FakeRedis:
    """SET NX / GET / EVAL with compare-and-delete semantics."""

    def __init__(self, *, broken: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.ops: Counter[str] = Counter()
        self.broken = broken

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        self.ops["set"] += 1
        if self.broken:
            raise ConnectionError("redis down")
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def eval(self, script: str, numkeys: int, *args):
        self.ops["eval"] += 1
        if self.broken:
            raise ConnectionError("redis down")
        key, token = args[0], args[1]
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0


class TestTryClaim:
    async def test_a_free_key_is_taken_with_the_owner_token(self) -> None:
        redis = FakeRedis()
        assert await try_claim(redis, "k", "owner-1", ttl_seconds=5) is True
        assert redis.store["k"] == "owner-1"

    async def test_a_held_key_is_refused(self) -> None:
        redis = FakeRedis()
        await try_claim(redis, "k", "owner-1", ttl_seconds=5)
        assert await try_claim(redis, "k", "owner-2", ttl_seconds=5) is False
        assert redis.store["k"] == "owner-1"

    async def test_a_cache_failure_propagates(self) -> None:
        """The primitive reports the truth; each caller decides whether a
        failure means "build anyway" (shared flight) or "refuse" (egress)."""
        with pytest.raises(ConnectionError):
            await try_claim(FakeRedis(broken=True), "k", "t", ttl_seconds=5)


class TestReleaseClaim:
    async def test_the_owner_releases(self) -> None:
        redis = FakeRedis()
        await try_claim(redis, "k", "owner-1", ttl_seconds=5)
        assert await release_claim(redis, "k", "owner-1") is True
        assert "k" not in redis.store

    async def test_a_successor_claim_is_never_deleted(self) -> None:
        """SET NX then an unconditional DELETE is the forbidden shape."""
        redis = FakeRedis()
        redis.store["k"] = "successor"
        assert await release_claim(redis, "k", "stale-owner") is False
        assert redis.store["k"] == "successor"

    async def test_a_cache_failure_on_release_is_swallowed(self) -> None:
        """A claim that could not be released expires by its TTL."""
        assert await release_claim(FakeRedis(broken=True), "k", "t") is False


class TestAcquireClaim:
    async def test_waits_for_a_holder_then_takes_over(self) -> None:
        redis = FakeRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=5)

        async def _holder_releases() -> None:
            await asyncio.sleep(0.03)
            await release_claim(redis, "k", "holder")

        asyncio.get_running_loop().create_task(_holder_releases())
        token = await acquire_claim(redis, "k", ttl_seconds=5, wait_seconds=1.0, poll_seconds=0.01)
        assert token is not None
        assert redis.store["k"] == token

    async def test_gives_up_when_the_budget_runs_out(self) -> None:
        redis = FakeRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=5)
        token = await acquire_claim(redis, "k", ttl_seconds=5, wait_seconds=0.05, poll_seconds=0.01)
        assert token is None
        assert redis.store["k"] == "holder"
