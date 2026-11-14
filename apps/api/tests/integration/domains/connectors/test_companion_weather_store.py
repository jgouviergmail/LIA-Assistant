"""The companion's weather on a REAL Redis: the newer observation always stays.

Four readers offer what they observed, at their own pace and from several workers.
A mocked cache cannot show two writers racing: only the script on the server keeps
an older observation from replacing a newer one (ADR-294, follow-up of 2026-11-13).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.constants import PRESENT_WEATHER_FRESH_SECONDS
from src.domains.connectors.companion_weather import (
    companion_weather_key,
    publish_companion_weather,
    read_companion_observation,
)
from src.infrastructure.cache.redis import get_redis_cache

pytestmark = pytest.mark.integration

MODULE = "src.domains.connectors.companion_weather"


def _reading(minutes_ago: int, temperature: float) -> dict[str, Any]:
    observed = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return {
        "dt": int(observed.timestamp()),
        "main": {"temp": temperature},
        "weather": [{"main": "Clear"}],
    }


async def test_a_newer_observation_replaces_an_older_one_and_never_the_reverse() -> None:
    user = uuid4()
    redis = await get_redis_cache()
    try:
        with patch(f"{MODULE}.publish_to_user", AsyncMock(return_value=True)) as said:
            assert await publish_companion_weather(user, _reading(20, 10.0)) is True
            assert await publish_companion_weather(user, _reading(5, 12.0)) is True
            # An older read landing late keeps the newer one.
            assert await publish_companion_weather(user, _reading(15, 8.0)) is False

        observation = await read_companion_observation(user)
        assert observation is not None and observation.temperature_c == 12.0
        assert said.await_count == 2
        # Kept as long as it stays the present, and no longer.
        ttl_ms = await redis.pttl(companion_weather_key(user))
        expected_ms = (PRESENT_WEATHER_FRESH_SECONDS - 5 * 60) * 1000
        assert expected_ms - 5_000 <= ttl_ms <= expected_ms
    finally:
        await redis.delete(companion_weather_key(user))


async def test_the_same_observation_offered_twice_is_said_once() -> None:
    # Two readers often receive the same provider observation (same instant):
    # the second changes nothing and must not make every open tab read again.
    user = uuid4()
    redis = await get_redis_cache()
    try:
        same = _reading(10, 9.0)
        with patch(f"{MODULE}.publish_to_user", AsyncMock(return_value=True)) as said:
            assert await publish_companion_weather(user, same) is True
            assert await publish_companion_weather(user, dict(same)) is False

        assert said.await_count == 1
    finally:
        await redis.delete(companion_weather_key(user))


async def test_racing_readers_leave_the_newest_observation() -> None:
    user = uuid4()
    redis = await get_redis_cache()
    try:
        with patch(f"{MODULE}.publish_to_user", AsyncMock(return_value=True)):
            await asyncio.gather(
                *(
                    publish_companion_weather(user, _reading(minutes, float(minutes)))
                    for minutes in range(1, 21)
                )
            )

        observation = await read_companion_observation(user)
        assert observation is not None and observation.temperature_c == 1.0
    finally:
        await redis.delete(companion_weather_key(user))
