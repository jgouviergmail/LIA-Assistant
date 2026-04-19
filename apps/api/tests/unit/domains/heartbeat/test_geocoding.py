"""Unit tests for domains/heartbeat/geocoding.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.heartbeat.geocoding import (
    _cache_key,
    _extract_city_name,
    resolve_city_name,
)


@pytest.mark.unit
def test_cache_key_uses_3_decimal_precision():
    assert _cache_key(48.85661, 2.35222) == "heartbeat:geocode:48.857:2.352"
    # Negative coords
    assert _cache_key(-33.8688, 151.2093) == "heartbeat:geocode:-33.869:151.209"


@pytest.mark.unit
def test_cache_key_same_bucket_for_nearby_coords():
    # Two points within ~100m should hash to the same key
    assert _cache_key(48.8566, 2.3522) == _cache_key(48.8568, 2.3521)


@pytest.mark.unit
def test_extract_city_name_prefers_name():
    entries = [{"name": "Paris", "country": "FR", "state": "Ile-de-France"}]
    assert _extract_city_name(entries) == "Paris"


@pytest.mark.unit
def test_extract_city_name_falls_back_to_state():
    entries = [{"country": "FR", "state": "Provence"}]
    assert _extract_city_name(entries) == "Provence"


@pytest.mark.unit
def test_extract_city_name_returns_none_on_empty():
    assert _extract_city_name([]) is None


@pytest.mark.unit
async def test_resolve_city_name_cache_hit_skips_api():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value="Lyon")
    with patch(
        "src.infrastructure.cache.redis.get_redis_cache",
        new=AsyncMock(return_value=redis),
    ):
        result = await resolve_city_name(45.75, 4.85, api_key="xxx")

    assert result == "Lyon"
    redis.set.assert_not_called()


@pytest.mark.unit
async def test_resolve_city_name_cache_miss_calls_api_and_caches():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()

    client = MagicMock()
    client.reverse_geocode = AsyncMock(return_value=[{"name": "Paris"}])

    with (
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=redis),
        ),
        patch(
            "src.domains.connectors.clients.openweathermap_client.OpenWeatherMapClient",
            return_value=client,
        ),
    ):
        result = await resolve_city_name(48.85, 2.35, api_key="xxx")

    assert result == "Paris"
    redis.set.assert_awaited_once()
    # Verify API was called
    client.reverse_geocode.assert_awaited_once_with(lat=48.85, lon=2.35, limit=1)


@pytest.mark.unit
async def test_resolve_city_name_returns_none_on_api_failure():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)

    client = MagicMock()
    client.reverse_geocode = AsyncMock(side_effect=RuntimeError("boom"))

    with (
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=redis),
        ),
        patch(
            "src.domains.connectors.clients.openweathermap_client.OpenWeatherMapClient",
            return_value=client,
        ),
    ):
        result = await resolve_city_name(48.85, 2.35, api_key="xxx")

    assert result is None


@pytest.mark.unit
async def test_resolve_city_name_skips_cache_when_redis_down():
    client = MagicMock()
    client.reverse_geocode = AsyncMock(return_value=[{"name": "Paris"}])

    with (
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.domains.connectors.clients.openweathermap_client.OpenWeatherMapClient",
            return_value=client,
        ),
    ):
        result = await resolve_city_name(48.85, 2.35, api_key="xxx")

    assert result == "Paris"
    client.reverse_geocode.assert_awaited_once()
