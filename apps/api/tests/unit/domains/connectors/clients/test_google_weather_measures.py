"""Received weather fields and requested units must describe the actual readings."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.google_weather_client import (
    GoogleWeatherClient,
    _epoch,
    _forecast_entry,
    _wind_entry,
)

pytestmark = pytest.mark.unit

PAYLOAD = {
    "currentTime": "2026-10-03T12:00:00Z",
    "interval": {"startTime": "2026-10-03T12:00:00Z"},
    "temperature": {"degrees": 0},
    "feelsLikeTemperature": {"degrees": -2},
    "dewPoint": {"degrees": -5},
    "heatIndex": {"degrees": 0},
    "windChill": {"degrees": -3},
    "wind": {"speed": {"value": 36}, "gust": {"value": 72}, "direction": {"degrees": 0}},
    "uvIndex": 0,
    "precipitation": {"probability": {"percent": 0}, "qpf": {"quantity": 0, "unit": "MILLIMETERS"}},
}


@pytest.mark.parametrize("value", [None, "bad", "2026-10-03", "2026-10-03T12:00:00"])
def test_unknown_provider_instants_never_become_now(value):
    with pytest.raises(ValueError):
        _epoch(value)


def test_received_gust_and_forecast_feels_like_are_not_dropped():
    assert _wind_entry(PAYLOAD)["gust"] == 20
    assert _forecast_entry(PAYLOAD)["main"]["feels_like"] == -2


@pytest.mark.asyncio
async def test_imperial_current_conditions_are_converted_once_without_an_extra_request():
    client = GoogleWeatherClient(uuid4())
    with (
        patch.object(client, "_resolve_point", new=AsyncMock(return_value=(0, 0, "Lyon", "FR"))),
        patch.object(client, "_make_request", new=AsyncMock(return_value=PAYLOAD)) as request,
        patch("src.domains.connectors.clients.google_weather_client.track_google_api_call"),
    ):
        weather = await client.get_current_weather(units="imperial")
    assert weather["main"]["temp"] == 32
    assert weather["main"]["feels_like"] == pytest.approx(28.4)
    assert weather["main"]["dew_point"] == 23
    assert weather["wind"]["speed"] == pytest.approx(22.3693629)
    assert weather["wind"]["gust"] == pytest.approx(44.7387258)
    assert weather["uvi"] == 0
    assert weather["pop"] == 0
    request.assert_awaited_once()


@pytest.mark.asyncio
async def test_paid_invalid_current_payload_is_accounted_before_projection_fails():
    client = GoogleWeatherClient(uuid4())
    payload = {**PAYLOAD, "currentTime": "bad"}
    with (
        patch.object(client, "_resolve_point", new=AsyncMock(return_value=(0, 0, "Lyon", "FR"))),
        patch.object(client, "_make_request", new=AsyncMock(return_value=payload)),
        patch(
            "src.domains.connectors.clients.google_weather_client.track_google_api_call"
        ) as tracked,
        pytest.raises(ValueError),
    ):
        await client.get_current_weather()
    tracked.assert_called_once_with("weather", "/v1/currentConditions:lookup", cached=False)


@pytest.mark.asyncio
async def test_imperial_forecast_is_converted_after_existing_three_hour_sampling():
    client = GoogleWeatherClient(uuid4())
    hourly = {"city": {"name": "Lyon"}, "list": [_forecast_entry(PAYLOAD) for _ in range(6)]}
    with patch.object(client, "get_hourly_forecast", new=AsyncMock(return_value=hourly)) as request:
        weather = await client.get_forecast(units="imperial", cnt=2)
    assert len(weather["list"]) == 2
    assert weather["list"][0]["main"]["temp"] == 32
    assert hourly["list"][0]["main"]["temp"] == 0
    request.assert_awaited_once()
