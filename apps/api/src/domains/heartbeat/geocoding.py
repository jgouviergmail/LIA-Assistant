"""Reverse geocoding helper for heartbeat weather notifications.

Resolves a (lat, lon) pair to a city name via OpenWeatherMap's reverse
geocoding API, with a Redis cache keyed on a coarse coordinate bucket
(3 decimals ≈ 100m). This minimizes API calls and lets the bucket be
safely shared between users since the key is derived from public
coordinates only.

Failures are swallowed and return ``None``: the notification content
can fall back to coordinates or omit the city entirely rather than
crash the heartbeat job.
"""

from __future__ import annotations

import structlog

from src.core.constants import LAST_KNOWN_LOCATION_GEOCODE_CACHE_TTL_SECONDS
from src.infrastructure.observability.metrics_heartbeat import (
    user_location_geocode_total,
)

logger = structlog.get_logger(__name__)

_REDIS_KEY_PREFIX = "heartbeat:geocode:"


def _cache_key(lat: float, lon: float) -> str:
    """Build a Redis key bucketed at 3 decimals (≈100m granularity)."""
    return f"{_REDIS_KEY_PREFIX}{lat:.3f}:{lon:.3f}"


def _extract_city_name(entries: list[dict]) -> str | None:
    """Pick a usable city/place label from an OpenWeatherMap reverse response.

    The API returns a list of candidates; we prefer ``name`` from the first
    entry, falling back to ``state`` or ``country`` if name is missing.
    """
    if not entries:
        return None
    first = entries[0]
    name = first.get("name")
    if name:
        return str(name)
    fallback = first.get("state") or first.get("country")
    return str(fallback) if fallback else None


async def resolve_city_name(
    lat: float,
    lon: float,
    api_key: str,
) -> str | None:
    """Return a human-readable city name for the given coordinates.

    Uses a Redis cache (TTL = ``LAST_KNOWN_LOCATION_GEOCODE_CACHE_TTL_SECONDS``)
    to avoid hammering the OpenWeatherMap geocoding API. On cache miss, calls
    the API, stores the result, and returns it. Returns ``None`` if Redis
    is down, the API fails, or no result is returned.

    Args:
        lat: Latitude in degrees.
        lon: Longitude in degrees.
        api_key: OpenWeatherMap API key for the user.

    Returns:
        The resolved city name, or ``None`` if unavailable.
    """
    cache_key = _cache_key(lat, lon)

    redis = None
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if redis is not None:
            cached = await redis.get(cache_key)
            if cached:
                user_location_geocode_total.labels(result="cache_hit").inc()
                return cached if isinstance(cached, str) else cached.decode()
    except Exception as exc:
        logger.debug("geocode_cache_read_failed", error=str(exc))

    if redis is None:
        user_location_geocode_total.labels(result="redis_down").inc()

    try:
        from src.domains.connectors.clients.openweathermap_client import (
            OpenWeatherMapClient,
        )

        client = OpenWeatherMapClient(api_key=api_key)
        entries = await client.reverse_geocode(lat=lat, lon=lon, limit=1)
    except Exception as exc:
        logger.warning("geocode_api_failed", error=str(exc))
        user_location_geocode_total.labels(result="api_error").inc()
        return None

    city = _extract_city_name(entries)
    if city is None:
        user_location_geocode_total.labels(result="api_error").inc()
        return None

    user_location_geocode_total.labels(result="api_hit").inc()

    if redis is not None:
        try:
            await redis.set(
                cache_key,
                city,
                ex=LAST_KNOWN_LOCATION_GEOCODE_CACHE_TTL_SECONDS,
            )
        except Exception as exc:
            logger.debug("geocode_cache_write_failed", error=str(exc))

    return city
