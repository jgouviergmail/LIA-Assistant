"""GoogleWeatherClient — OWM-shaped normalization contract (lot E, 2026-08).

LIA's internal weather shape is the OpenWeatherMap JSON (19 call sites).
This client normalizes the Google Weather API at its boundary so every
consumer (tools, briefing, heartbeat, proactive) works unchanged whichever
provider the user activates. The field mapping and unit conversions ARE the
contract — pinned here.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.google_weather_client import GoogleWeatherClient

pytestmark = pytest.mark.unit

_CURRENT_PAYLOAD: dict[str, Any] = {
    "temperature": {"degrees": 20.4, "unit": "CELSIUS"},
    "feelsLikeTemperature": {"degrees": 24.5, "unit": "CELSIUS"},
    "relativeHumidity": 65,
    "airPressure": {"meanSeaLevelMillibars": 1015.2},
    "weatherCondition": {
        "description": {"text": "Nuageux", "languageCode": "fr"},
        "type": "CLOUDY",
        "iconBaseUri": "https://maps.gstatic.com/weather/v1/cloudy",
    },
    "precipitation": {"probability": {"percent": 10, "type": "RAIN"}},
    "wind": {
        "direction": {"degrees": 180},
        "speed": {"value": 18.0, "unit": "KILOMETERS_PER_HOUR"},
    },
    "visibility": {"distance": 10.0, "unit": "KILOMETERS"},
    "cloudCover": 92,
    "isDaytime": True,
    "currentConditionsHistory": {
        "maxTemperature": {"degrees": 26.0},
        "minTemperature": {"degrees": 15.0},
    },
}


@pytest.fixture
def client() -> GoogleWeatherClient:
    return GoogleWeatherClient(uuid4())


@pytest.fixture
def request_spy(client: GoogleWeatherClient) -> AsyncMock:
    spy = AsyncMock(return_value=dict(_CURRENT_PAYLOAD))
    client._make_request = spy  # type: ignore[method-assign]
    return spy


class TestCurrentWeatherMapping:
    async def test_owm_shape_with_metric_conversions(
        self, client: GoogleWeatherClient, request_spy: AsyncMock
    ) -> None:
        weather = await client.get_current_weather(lat=48.85, lon=2.35, lang="fr")

        assert weather["main"]["temp"] == 20.4
        assert weather["main"]["feels_like"] == 24.5
        assert weather["main"]["humidity"] == 65
        assert weather["main"]["pressure"] == 1015.2
        assert weather["main"]["temp_min"] == 15.0
        assert weather["main"]["temp_max"] == 26.0
        assert weather["weather"][0]["description"] == "Nuageux"
        assert weather["weather"][0]["main"] == "CLOUDY"
        # 18 km/h -> 5.0 m/s (OWM metric wind unit)
        assert weather["wind"]["speed"] == 5.0
        assert weather["wind"]["deg"] == 180
        assert weather["clouds"]["all"] == 92
        # 10 km -> 10000 m (OWM visibility unit)
        assert weather["visibility"] == 10000
        assert isinstance(weather["dt"], int)

    async def test_request_uses_metric_and_language(
        self, client: GoogleWeatherClient, request_spy: AsyncMock
    ) -> None:
        await client.get_current_weather(lat=48.85, lon=2.35, lang="fr")
        params = request_spy.call_args.kwargs["params"]
        assert params["location.latitude"] == 48.85
        assert params["location.longitude"] == 2.35
        assert params["unitsSystem"] == "METRIC"
        assert params["languageCode"] == "fr"

    async def test_city_and_country_ride_along_when_known(
        self, client: GoogleWeatherClient, request_spy: AsyncMock
    ) -> None:
        with patch(
            "src.domains.connectors.clients.google_weather_client.forward_geocode",
            new=AsyncMock(return_value=(48.85, 2.35, "Paris", "FR")),
        ):
            weather = await client.get_current_weather(city="Paris", lang="fr")
        assert weather["name"] == "Paris"
        assert weather["sys"]["country"] == "FR"

    async def test_call_is_tracked(
        self, client: GoogleWeatherClient, request_spy: AsyncMock
    ) -> None:
        with patch(
            "src.domains.connectors.clients.google_weather_client.track_google_api_call"
        ) as tracker:
            await client.get_current_weather(lat=1.0, lon=2.0)
        tracker.assert_any_call("weather", "/v1/currentConditions:lookup", cached=False)


class TestIconMapping:
    @pytest.mark.parametrize(
        ("condition_type", "is_daytime", "expected"),
        [
            ("CLEAR", True, "01d"),
            ("CLEAR", False, "01n"),
            ("PARTLY_CLOUDY", True, "02d"),
            ("CLOUDY", True, "04d"),
            ("RAIN", True, "10d"),
            ("SNOW", False, "13n"),
            ("THUNDERSTORM", True, "11d"),
            ("SOME_FUTURE_TYPE", True, "03d"),  # unknown → neutral fallback
        ],
    )
    async def test_google_types_map_to_owm_icon_codes(
        self,
        client: GoogleWeatherClient,
        request_spy: AsyncMock,
        condition_type: str,
        is_daytime: bool,
        expected: str,
    ) -> None:
        payload = dict(_CURRENT_PAYLOAD)
        payload["weatherCondition"] = {"description": {"text": "x"}, "type": condition_type}
        payload["isDaytime"] = is_daytime
        request_spy.return_value = payload

        weather = await client.get_current_weather(lat=1.0, lon=2.0)

        assert weather["weather"][0]["icon"] == expected


def _hour(iso: str, temp: float) -> dict[str, Any]:
    return {
        "interval": {"startTime": iso},
        "temperature": {"degrees": temp},
        "relativeHumidity": 50,
        "weatherCondition": {"description": {"text": "clair"}, "type": "CLEAR"},
        "isDaytime": True,
        "precipitation": {"probability": {"percent": 20}},
        "wind": {
            "direction": {"degrees": 90},
            "speed": {"value": 9.0, "unit": "KILOMETERS_PER_HOUR"},
        },
    }


class TestForecastMapping:
    async def test_hourly_sampled_to_owm_three_hour_entries(
        self, client: GoogleWeatherClient, request_spy: AsyncMock
    ) -> None:
        request_spy.return_value = {
            "forecastHours": [
                _hour(f"2026-08-27T{hour:02d}:00:00Z", 20.0 + hour) for hour in range(6)
            ]
        }

        forecast = await client.get_forecast(lat=48.85, lon=2.35, cnt=2)

        entries = forecast["list"]
        assert len(entries) == 2  # 6 hourly entries sampled every 3 hours
        assert entries[0]["main"]["temp"] == 20.0
        assert entries[1]["main"]["temp"] == 23.0
        assert entries[0]["pop"] == 0.2  # OWM pop is 0..1
        assert entries[0]["wind"]["speed"] == 2.5  # 9 km/h -> m/s
        assert isinstance(entries[0]["dt"], int)
        assert "city" in forecast

    async def test_pagination_follows_next_page_token(
        self, client: GoogleWeatherClient, request_spy: AsyncMock
    ) -> None:
        request_spy.side_effect = [
            {
                "forecastHours": [
                    _hour(f"2026-08-27T{hour:02d}:00:00Z", 20.0 + hour) for hour in range(3)
                ],
                "nextPageToken": "page2",
            },
            {
                "forecastHours": [
                    _hour(f"2026-08-27T{hour:02d}:00:00Z", 20.0 + hour) for hour in range(3, 6)
                ]
            },
        ]

        forecast = await client.get_forecast(lat=1.0, lon=2.0, cnt=2)

        assert request_spy.call_count == 2
        assert request_spy.call_args_list[1].kwargs["params"]["pageToken"] == "page2"
        assert len(forecast["list"]) == 2
        assert forecast["list"][1]["main"]["temp"] == 23.0


class TestDailyForecast:
    async def test_delegates_to_the_shared_aggregation(self, client: GoogleWeatherClient) -> None:
        client.get_forecast = AsyncMock(  # type: ignore[method-assign]
            return_value={
                "list": [
                    {
                        "dt": 1_787_000_000,
                        "main": {"temp": 20.0, "humidity": 50},
                        "weather": [{"description": "clair"}],
                        "wind": {"speed": 2.0},
                    }
                ],
                "city": {"name": "Paris"},
            }
        )

        result = await client.get_daily_forecast(
            lat=1.0, lon=2.0, days=1, user_timezone="Europe/Paris"
        )

        assert result["city"] == {"name": "Paris"}
        assert result["daily"][0]["temp_min"] == 20.0
        assert result["daily"][0]["condition"] == "clair"


class TestGeocodeDelegation:
    async def test_geocode_delegates_to_google_geocoding(self, client: GoogleWeatherClient) -> None:
        with patch(
            "src.domains.connectors.clients.google_weather_client.forward_geocode",
            new=AsyncMock(return_value=(48.85, 2.35, "Paris", "FR")),
        ):
            results = await client.geocode("Paris")
        assert results == [{"lat": 48.85, "lon": 2.35, "name": "Paris", "country": "FR"}]

    async def test_geocode_no_result_is_empty_list(self, client: GoogleWeatherClient) -> None:
        with patch(
            "src.domains.connectors.clients.google_weather_client.forward_geocode",
            new=AsyncMock(return_value=None),
        ):
            assert await client.geocode("Nowhere-Ville-Inconnue") == []
