"""Integration: the per-person turn claim against real Redis (ADR-323 review).

The unit tests fake the cache: a mock whose ``eval`` always answers 1 never runs
the compare-and-delete script, so a stale holder freeing its successor's claim
would stay green. Here two actors race on one key of a real Redis — the first
outlives its claim, the second takes it — and the first's late release must
leave the second's claim alone.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.core.constants import CHANNEL_MESSAGE_LOCK_PREFIX
from src.domains.channels.message_router import hold_turn_claim, take_turn_claim
from src.infrastructure.locks.redis_claim import (
    ClaimLost,
    held_claim,
    release_claim,
    try_claim,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    try:
        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.ping()
    except Exception as exc:  # noqa: BLE001 — environment guard, not logic
        pytest.skip(f"Redis not available: {exc}")
    yield redis
    await redis.aclose()


async def test_a_stale_holder_never_releases_its_successor_s_claim(redis_client: Redis) -> None:
    key = f"{CHANNEL_MESSAGE_LOCK_PREFIX}test-{uuid.uuid4().hex}"
    try:
        assert await try_claim(redis_client, key, "first", ttl_seconds=1)
        assert not await try_claim(redis_client, key, "second", ttl_seconds=30)

        await asyncio.sleep(1.3)  # the first holder outlived its claim
        assert await try_claim(redis_client, key, "second", ttl_seconds=30)

        assert not await release_claim(redis_client, key, "first")  # stale: refused
        assert await redis_client.get(key) == "second"
        assert await release_claim(redis_client, key, "second")
        assert await redis_client.get(key) is None
    finally:
        await redis_client.delete(key)


async def test_a_message_and_a_button_share_the_person_s_turn(redis_client: Redis) -> None:
    user_id = uuid.uuid4()
    key = f"{CHANNEL_MESSAGE_LOCK_PREFIX}{user_id}"
    try:
        token = await take_turn_claim(redis_client, user_id)
        assert token is not None
        async with hold_turn_claim(redis_client, user_id, token):
            # A second door (a button pressed during the turn) finds it taken.
            assert await take_turn_claim(redis_client, user_id) is None
        assert await redis_client.get(key) is None
        assert await take_turn_claim(redis_client, user_id) is not None
    finally:
        await redis_client.delete(key)


async def test_a_turn_outlives_the_claim_s_ttl(redis_client: Redis) -> None:
    """Held, the claim lives as long as the turn — the next message finds it
    taken past the TTL, and it is free again once the turn ended."""
    key = f"{CHANNEL_MESSAGE_LOCK_PREFIX}test-{uuid.uuid4().hex}"
    try:
        assert await try_claim(redis_client, key, "turn", ttl_seconds=1)
        async with held_claim(redis_client, key, "turn", ttl_seconds=1, refresh_seconds=0.2):
            await asyncio.sleep(1.5)
            assert not await try_claim(redis_client, key, "next", ttl_seconds=30)
        assert await redis_client.get(key) is None
    finally:
        await redis_client.delete(key)


async def test_a_turn_whose_claim_another_took_is_stopped(redis_client: Redis) -> None:
    key = f"{CHANNEL_MESSAGE_LOCK_PREFIX}test-{uuid.uuid4().hex}"
    effects: list[str] = []
    try:
        assert await try_claim(redis_client, key, "first", ttl_seconds=30)
        with pytest.raises(ClaimLost) as lost:
            async with held_claim(redis_client, key, "first", ttl_seconds=30, refresh_seconds=0.1):
                # The claim expired during an outage and the next turn took it.
                await redis_client.delete(key)
                assert await try_claim(redis_client, key, "second", ttl_seconds=30)
                await asyncio.sleep(1)
                effects.append("written beside the second turn")

        assert lost.value.reason == "taken_over"
        assert effects == []
        assert await redis_client.get(key) == "second"
    finally:
        await redis_client.delete(key)
