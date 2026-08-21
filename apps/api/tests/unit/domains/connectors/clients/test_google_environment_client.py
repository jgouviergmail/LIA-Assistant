"""Google Environment client — Air Quality + Pollen (lot E, 2026-08).

Platform-key client behind the GOOGLE_ENVIRONMENT toggle. Normalized outputs
are the tool contract: exact indices from the API aggregates, never derived.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.google_environment_client import GoogleEnvironmentClient

pytestmark = pytest.mark.unit

_AQ_PAYLOAD: dict[str, Any] = {
    "dateTime": "2026-08-21T09:00:00Z",
    "regionCode": "fr",
    "indexes": [
        {
            "code": "uaqi",
            "displayName": "Universal AQI",
            "aqi": 77,
            "category": "Good air quality",
            "dominantPollutant": "pm10",
        },
        {
            "code": "fra_atmo",
            "displayName": "ATMO (France)",
            "aqi": 2,
            "category": "Moyen",
            "dominantPollutant": "pm10",
        },
    ],
}

_POLLEN_PAYLOAD: dict[str, Any] = {
    "regionCode": "FR",
    "dailyInfo": [
        {
            "date": {"year": 2026, "month": 8, "day": 21},
            "pollenTypeInfo": [
                {
                    "code": "GRASS",
                    "displayName": "Graminées",
                    "inSeason": True,
                    "indexInfo": {"value": 3, "category": "Modéré"},
                },
                {
                    "code": "TREE",
                    "displayName": "Arbres",
                    "inSeason": False,
                },
            ],
        }
    ],
}


@pytest.fixture
def client() -> GoogleEnvironmentClient:
    return GoogleEnvironmentClient(uuid4())


class TestAirQuality:
    async def test_normalizes_all_indexes_with_exact_values(
        self, client: GoogleEnvironmentClient
    ) -> None:
        spy = AsyncMock(return_value=dict(_AQ_PAYLOAD))
        client._make_request = spy  # type: ignore[method-assign]

        result = await client.get_air_quality(lat=48.85, lon=2.35, language="fr")

        assert result["indexes"][0] == {
            "code": "uaqi",
            "display_name": "Universal AQI",
            "aqi": 77,
            "category": "Good air quality",
            "dominant_pollutant": "pm10",
        }
        assert len(result["indexes"]) == 2
        assert result["region_code"] == "fr"

    async def test_requests_local_index_and_language(self, client: GoogleEnvironmentClient) -> None:
        spy = AsyncMock(return_value=dict(_AQ_PAYLOAD))
        client._make_request = spy  # type: ignore[method-assign]

        await client.get_air_quality(lat=48.85, lon=2.35, language="fr")

        body = spy.call_args.kwargs["json_data"]
        assert body["location"] == {"latitude": 48.85, "longitude": 2.35}
        assert body["languageCode"] == "fr"
        # The local (national) index matters to the user as much as UAQI.
        assert {"code": "LOCAL_AQI"} in body["extraComputations"] or body["extraComputations"]

    async def test_call_is_tracked(self, client: GoogleEnvironmentClient) -> None:
        client._make_request = AsyncMock(return_value=dict(_AQ_PAYLOAD))  # type: ignore[method-assign]
        with patch(
            "src.domains.connectors.clients.google_environment_client.track_google_api_call"
        ) as tracker:
            await client.get_air_quality(lat=1.0, lon=2.0)
        tracker.assert_any_call("air_quality", "/v1/currentConditions:lookup", cached=False)


class TestPollen:
    async def test_normalizes_daily_pollen_types(self, client: GoogleEnvironmentClient) -> None:
        spy = AsyncMock(return_value=dict(_POLLEN_PAYLOAD))
        client._make_request = spy  # type: ignore[method-assign]

        result = await client.get_pollen_forecast(lat=48.85, lon=2.35, days=1, language="fr")

        day = result["days"][0]
        assert day["date"] == "2026-08-21"
        grass = day["types"][0]
        assert grass == {
            "code": "GRASS",
            "display_name": "Graminées",
            "in_season": True,
            "index_value": 3,
            "category": "Modéré",
        }
        # Types without an index (out of season) still appear, honestly empty.
        assert day["types"][1]["in_season"] is False
        assert day["types"][1]["index_value"] is None

    async def test_days_is_clamped_to_api_bounds(self, client: GoogleEnvironmentClient) -> None:
        spy = AsyncMock(return_value=dict(_POLLEN_PAYLOAD))
        client._make_request = spy  # type: ignore[method-assign]

        await client.get_pollen_forecast(lat=1.0, lon=2.0, days=99)

        assert spy.call_args.kwargs["params"]["days"] == 5

    async def test_call_is_tracked(self, client: GoogleEnvironmentClient) -> None:
        client._make_request = AsyncMock(return_value=dict(_POLLEN_PAYLOAD))  # type: ignore[method-assign]
        with patch(
            "src.domains.connectors.clients.google_environment_client.track_google_api_call"
        ) as tracker:
            await client.get_pollen_forecast(lat=1.0, lon=2.0)
        tracker.assert_any_call("pollen", "/v1/forecast:lookup", cached=False)
