"""Air-quality/pollen enrichment of plain weather answers (2026-08).

When the user activated the Google Environment connector, a simple weather
question also gets the air quality and any in-season pollen signal — without
a separate request. Contract:

- Connector inactive (or platform key missing) → None, zero API calls.
- Best-effort: any API failure → None (a weather answer never breaks on an
  enrichment).
- Redis-cached per coordinate bucket + language (billed APIs, weather-scale
  change rate).
- The LOCAL (national) index wins over the universal one when present; the
  category string is the API's own localized wording (the UAQI scale is
  inverted vs EPA — never re-derive a label from the number).
- Pollen keeps only in-season types with a real index value.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools import weather_environment_enrichment as enrichment

pytestmark = pytest.mark.unit

_AQ_PAYLOAD: dict[str, Any] = {
    "region_code": "fr",
    "date_time": "2026-08-21T16:00:00Z",
    "indexes": [
        {
            "code": "uaqi",
            "display_name": "Universal AQI",
            "aqi": 71,
            "category": "Good air quality",
            "dominant_pollutant": "o3",
        },
        {
            "code": "fra_atmo",
            "display_name": "ATMO",
            "aqi": 3,
            "category": "Dégradé",
            "dominant_pollutant": "o3",
        },
    ],
}

_POLLEN_PAYLOAD: dict[str, Any] = {
    "region_code": "fr",
    "days": [
        {
            "date": "2026-08-21",
            "types": [
                {
                    "code": "GRASS",
                    "display_name": "Graminées",
                    "in_season": True,
                    "index_value": 4,
                    "category": "Élevé",
                },
                {
                    "code": "TREE",
                    "display_name": "Arbres",
                    "in_season": False,
                    "index_value": None,
                    "category": "",
                },
            ],
        }
    ],
}


def _redis(cached: str | None = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock()
    return redis


def _client() -> MagicMock:
    client = MagicMock()
    client.get_air_quality = AsyncMock(return_value=dict(_AQ_PAYLOAD))
    client.get_pollen_forecast = AsyncMock(return_value=dict(_POLLEN_PAYLOAD))
    return client


def _service(active: bool = True) -> MagicMock:
    service = MagicMock()
    service.is_connector_active = AsyncMock(return_value=active)
    return service


class TestEnvironmentExtras:
    async def test_inactive_connector_returns_none_without_calls(self) -> None:
        client = _client()
        with (
            patch.object(enrichment, "GoogleEnvironmentClient", return_value=client),
            patch.object(enrichment.settings, "google_api_key", "key"),
            patch.object(enrichment, "_get_redis", new=AsyncMock(return_value=_redis())),
        ):
            extras = await enrichment.environment_extras_or_none(
                uuid4(), _service(active=False), 48.85, 2.35, "fr"
            )
        assert extras is None
        client.get_air_quality.assert_not_awaited()

    async def test_active_connector_returns_local_index_and_in_season_pollen(self) -> None:
        client = _client()
        with (
            patch.object(enrichment, "GoogleEnvironmentClient", return_value=client),
            patch.object(enrichment.settings, "google_api_key", "key"),
            patch.object(enrichment, "_get_redis", new=AsyncMock(return_value=_redis())),
        ):
            extras = await enrichment.environment_extras_or_none(
                uuid4(), _service(), 48.85, 2.35, "fr"
            )
        assert extras is not None
        # The national index (ATMO) wins over the universal one.
        assert extras["aqi"] == 3
        assert extras["aqi_category"] == "Dégradé"
        # Only the in-season type with a real index survives.
        assert extras["pollen"] == [{"name": "Graminées", "category": "Élevé", "index": 4}]

    async def test_local_index_without_a_number_keeps_its_category(self) -> None:
        # MEASURED in prod (2026-08-21): the French national index `fra_atmo`
        # carries a category ("Moyen") but NO `aqi` field at all. Dropping the
        # whole enrichment — or pairing that label with the universal index's
        # number — would be wrong; the honest answer is the category alone.
        client = _client()
        client.get_air_quality = AsyncMock(
            return_value={
                "indexes": [
                    {
                        "code": "uaqi",
                        "display_name": "Universal AQI",
                        "aqi": 66,
                        "category": "Bonne qualité de l'air",
                    },
                    {
                        "code": "fra_atmo",
                        "display_name": "IQA (FR)",
                        "aqi": None,
                        "category": "Moyen",
                    },
                ]
            }
        )
        with (
            patch.object(enrichment, "GoogleEnvironmentClient", return_value=client),
            patch.object(enrichment.settings, "google_api_key", "key"),
            patch.object(enrichment, "_get_redis", new=AsyncMock(return_value=_redis())),
        ):
            extras = await enrichment.environment_extras_or_none(
                uuid4(), _service(), 48.85, 2.35, "fr"
            )
        assert extras is not None
        assert extras["aqi_category"] == "Moyen"
        assert extras["aqi_label"] == "IQA (FR)"
        # The number belongs to the OTHER scale — never grafted onto this label.
        assert extras["aqi"] is None
        # And the enrichment stays usable (a category alone is a real signal).
        assert extras["has_air_quality"] is True

    async def test_index_without_category_nor_value_is_not_air_quality(self) -> None:
        client = _client()
        client.get_air_quality = AsyncMock(
            return_value={"indexes": [{"code": "uaqi", "display_name": "U", "aqi": None}]}
        )
        with (
            patch.object(enrichment, "GoogleEnvironmentClient", return_value=client),
            patch.object(enrichment.settings, "google_api_key", "key"),
            patch.object(enrichment, "_get_redis", new=AsyncMock(return_value=_redis())),
        ):
            extras = await enrichment.environment_extras_or_none(
                uuid4(), _service(), 48.85, 2.35, "fr"
            )
        assert extras is not None
        assert extras["has_air_quality"] is False

    async def test_uaqi_fallback_when_no_local_index(self) -> None:
        client = _client()
        client.get_air_quality = AsyncMock(
            return_value={"indexes": [dict(_AQ_PAYLOAD["indexes"][0])]}
        )
        with (
            patch.object(enrichment, "GoogleEnvironmentClient", return_value=client),
            patch.object(enrichment.settings, "google_api_key", "key"),
            patch.object(enrichment, "_get_redis", new=AsyncMock(return_value=_redis())),
        ):
            extras = await enrichment.environment_extras_or_none(
                uuid4(), _service(), 48.85, 2.35, "fr"
            )
        assert extras is not None
        assert extras["aqi"] == 71
        assert extras["aqi_category"] == "Good air quality"

    async def test_api_failure_is_fail_quiet(self) -> None:
        client = _client()
        client.get_air_quality = AsyncMock(side_effect=RuntimeError("api down"))
        with (
            patch.object(enrichment, "GoogleEnvironmentClient", return_value=client),
            patch.object(enrichment.settings, "google_api_key", "key"),
            patch.object(enrichment, "_get_redis", new=AsyncMock(return_value=_redis())),
        ):
            extras = await enrichment.environment_extras_or_none(
                uuid4(), _service(), 48.85, 2.35, "fr"
            )
        assert extras is None

    def test_registry_payload_carries_the_extras(self) -> None:
        # The card reads the RegistryItem payload: the enrichment must land
        # there (aqi/aqi_category/pollen), and be absent when not fetched.
        from src.domains.agents.tools.weather_tools import GetCurrentWeatherTool

        tool = GetCurrentWeatherTool(tool_name="get_current_weather_tool", operation="read")
        base_result: dict[str, Any] = {
            "success": True,
            "data": {
                "location": {"name": "Paris", "country": "FR"},
                "weather": {"temperature": "21°C", "description": "ciel dégagé"},
            },
            "_language": "fr",
        }
        enriched = dict(base_result)
        enriched["data"] = {
            **base_result["data"],
            "environment": {
                "aqi": 3,
                "aqi_category": "Dégradé",
                "pollen": [{"name": "Graminées", "category": "Élevé", "index": 4}],
            },
        }

        output = tool.format_registry_response(enriched)
        payload = next(iter(output.registry_updates.values())).payload
        assert payload["aqi"] == 3
        assert payload["aqi_category"] == "Dégradé"
        assert payload["pollen"] == [{"name": "Graminées", "category": "Élevé", "index": 4}]

        bare = tool.format_registry_response(dict(base_result))
        bare_payload = next(iter(bare.registry_updates.values())).payload
        assert "aqi" not in bare_payload
        assert "pollen" not in bare_payload

    async def test_cache_hit_skips_the_billed_calls(self) -> None:
        cached = '{"aqi": 2, "aqi_category": "Bon", "pollen": []}'
        client = _client()
        with (
            patch.object(enrichment, "GoogleEnvironmentClient", return_value=client),
            patch.object(enrichment.settings, "google_api_key", "key"),
            patch.object(enrichment, "_get_redis", new=AsyncMock(return_value=_redis(cached))),
        ):
            extras = await enrichment.environment_extras_or_none(
                uuid4(), _service(), 48.85, 2.35, "fr"
            )
        assert extras == {"aqi": 2, "aqi_category": "Bon", "pollen": []}
        client.get_air_quality.assert_not_awaited()
        client.get_pollen_forecast.assert_not_awaited()
