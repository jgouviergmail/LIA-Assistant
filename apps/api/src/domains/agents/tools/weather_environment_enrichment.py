"""Air-quality/pollen enrichment of plain weather answers (2026-08).

When the user activated the Google Environment connector, a simple weather
question also carries the air quality and any in-season pollen signal —
no separate request needed. Strictly best-effort: a weather answer must
never fail or slow down because an enrichment could not be fetched.

Cost control: both APIs are billed (AQ $5/1000, Pollen $10/1000), so the
result is Redis-cached per coordinate bucket (3 decimals ≈ 100 m) and
language, with a weather-scale TTL. A cache hit costs nothing and is not
tracked (only real API calls are billed).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.connectors.clients.google_environment_client import GoogleEnvironmentClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

_CACHE_PREFIX = "weather:environment:"


async def _get_redis() -> Any:
    """Late import: keeps this module importable without the cache stack."""
    from src.infrastructure.cache.redis import get_redis_cache

    return await get_redis_cache()


def _cache_key(lat: float, lon: float, language: str) -> str:
    """Coordinate bucket (3 decimals ≈ 100 m) + language (localized labels)."""
    return f"{_CACHE_PREFIX}{lat:.3f}:{lon:.3f}:{language}"


def _pick_aqi(indexes: list[dict[str, Any]]) -> tuple[Any, str, str]:
    """(value, category, label) of the most meaningful index.

    The LOCAL (national) index wins over the universal one: "IQA (FR) —
    Moyen" speaks to a French user where "UAQI 66" does not. The category
    string is the API's own localized wording — the UAQI scale is INVERTED
    vs EPA (100 = excellent), so a label must never be re-derived from the
    number.

    A number and a label must come from the SAME index (measured 2026-08-21
    in prod: ``fra_atmo`` ships a category with NO ``aqi`` field at all).
    Grafting the universal index's number onto the national label would state
    a value on the wrong scale; the honest answer is the category alone, so
    the value is returned only when the CHOSEN index carries it.
    """
    local = next(
        (i for i in indexes if i.get("code") not in ("", "uaqi") and i.get("category")),
        None,
    )
    chosen = local or (indexes[0] if indexes else None)
    if chosen is None:
        return None, "", ""
    return (
        chosen.get("aqi"),
        str(chosen.get("category", "")),
        str(chosen.get("display_name", "")),
    )


def _in_season_pollen(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Today's in-season pollen types with a real index (honest signal only)."""
    days = payload.get("days") or []
    if not days:
        return []
    return [
        {
            "name": entry.get("display_name", ""),
            "category": entry.get("category", ""),
            "index": entry.get("index_value"),
        }
        for entry in days[0].get("types", [])
        if entry.get("in_season") and entry.get("index_value") is not None
    ]


async def environment_extras_or_none(
    user_id: UUID,
    connector_service: Any,
    lat: float,
    lon: float,
    language: str,
) -> dict[str, Any] | None:
    """Air quality + in-season pollen for a point, or None (fail-quiet).

    Args:
        user_id: Owner of the connectors (billing attribution).
        connector_service: ConnectorService for the activation check.
        lat: Latitude of the weather query point.
        lon: Longitude of the weather query point.
        language: User language (labels come localized from the API).

    Returns:
        ``{"aqi", "aqi_category", "aqi_label", "has_air_quality",
        "pollen": [{name, category, index}]}`` when the Google Environment
        connector is active and the data is available; None otherwise — the
        caller simply skips the enrichment. ``has_air_quality`` is the flag
        consumers render on: ``aqi`` is legitimately None for national
        indexes that publish a category and no number.
    """
    try:
        if not settings.google_api_key:
            return None
        if not await connector_service.is_connector_active(
            user_id, ConnectorType.GOOGLE_ENVIRONMENT
        ):
            return None

        redis = None
        cache_key = _cache_key(lat, lon, language)
        try:
            redis = await _get_redis()
            cached = await redis.get(cache_key)
            if cached:
                return dict(json.loads(cached))
        except Exception as exc:
            logger.debug("environment_enrichment_cache_read_failed", error=str(exc))

        # Two independent HTTP calls on the CHAT latency path — run them
        # together rather than back to back (no shared DB session involved,
        # so this is safe; the client paces itself internally).
        client = GoogleEnvironmentClient(user_id)
        air_quality, pollen = await asyncio.gather(
            client.get_air_quality(lat=lat, lon=lon, language=language),
            client.get_pollen_forecast(lat=lat, lon=lon, days=1, language=language),
        )

        aqi, category, label = _pick_aqi(air_quality.get("indexes", []))
        extras = {
            "aqi": aqi,
            "aqi_category": category,
            "aqi_label": label,
            # Explicit: a category alone IS air quality (the national index
            # often has no number); nothing at all is not. Consumers render
            # on this flag instead of re-deriving truthiness from a value
            # that is legitimately None.
            "has_air_quality": bool(category) or aqi is not None,
            "pollen": _in_season_pollen(pollen),
        }

        if redis is not None:
            try:
                await redis.set(
                    cache_key,
                    json.dumps(extras),
                    ex=settings.weather_environment_enrichment_ttl_seconds,
                )
            except Exception as exc:
                logger.debug("environment_enrichment_cache_write_failed", error=str(exc))

        return extras
    except Exception as exc:
        # Best-effort by contract: the weather answer never breaks on this.
        logger.warning("environment_enrichment_failed", error=str(exc))
        return None


async def attach_environment_extras(
    formatted: dict[str, Any],
    runtime: Any,
    user_id: UUID,
    lat: float,
    lon: float,
    language: str,
) -> None:
    """Attach the extras to a formatted weather result, in place (fail-quiet).

    One-line call site for the weather tools: resolves the connector service
    from the runtime, fetches the extras, and stores them under
    ``formatted["data"]["environment"]`` — or does strictly nothing.
    """
    try:
        if runtime is None or formatted.get("data") is None:
            return
        from src.domains.agents.dependencies import get_dependencies

        connector_service = await get_dependencies(runtime).get_connector_service()
        extras = await environment_extras_or_none(user_id, connector_service, lat, lon, language)
        if extras is not None:
            formatted["data"]["environment"] = extras
    except Exception as exc:
        # WARNING, not debug: prod runs at INFO, and a silent attach failure
        # is exactly what made this enrichment look "not deployed" for an
        # afternoon (2026-08-21). Rare by construction, so no log noise.
        logger.warning("environment_enrichment_attach_failed", error=str(exc))


def environment_payload_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Registry-payload fields from an enriched result ({} when not enriched).

    An absent key means "not enriched" — never a fabricated value.
    """
    extras = data.get("environment")
    if not extras:
        return {}
    return {
        "aqi": extras.get("aqi"),
        "aqi_category": extras.get("aqi_category"),
        "aqi_label": extras.get("aqi_label", ""),
        "has_air_quality": extras.get("has_air_quality", False),
        "pollen": extras.get("pollen", []),
    }
