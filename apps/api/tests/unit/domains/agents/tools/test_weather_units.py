"""The weather tools serve the units they publish, and refuse the ones they cannot read (ADR-310)."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.weather_formatting import read_units, unreadable_units_result
from src.domains.agents.tools.weather_tools import _get_weather_forecast_tool_impl
from src.domains.agents.weather.catalogue_manifests import WEATHER_UNITS

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "served"),
    [
        (None, "metric"),
        ("", "metric"),
        ("metric", "metric"),
        (" IMPERIAL ", "imperial"),
        ("Celsius", "metric"),
        ("fahrenheit", "imperial"),
    ],
)
def test_readable_units_are_served(raw: object, served: str) -> None:
    assert read_units(raw) == served


@pytest.mark.parametrize("raw", ["standard", "kelvin", "METRIC_SI", 1, ["metric"]])
def test_unreadable_units_are_refused_not_sent(raw: object) -> None:
    assert read_units(raw) is None
    result = unreadable_units_result(raw)
    assert result["success"] is False
    assert result["error_code"] == ToolErrorCode.INVALID_INPUT.value
    assert all(unit in result["message"] for unit in WEATHER_UNITS)


async def test_the_forecast_tool_refuses_before_calling_the_provider() -> None:

    client = AsyncMock()
    result = await _get_weather_forecast_tool_impl.execute_api_call(
        client, uuid4(), location="Montbéliard", runtime=None, units="kelvin"
    )
    assert result["error"] == "invalid_units"
    client.get_daily_forecast.assert_not_awaited()
