"""The daily forecast returns the window it was asked for, or says why not.

2026-10-11: "the next five days" was planned as date=today, days=5 and came
back as ONE day — an explicit days equal to the default was replaced by 1.
Thresholds are read from settings, never hardcoded.
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.config import get_settings
from src.domains.agents.tools import weather_tools
from src.domains.agents.tools.weather_dates import forecast_window_days
from src.domains.agents.tools.weather_tools import _get_weather_forecast_tool_impl
from src.domains.agents.weather.catalogue_manifests import _DAYS_PARAM, FORECAST_DAYS_DESCRIPTION

pytestmark = pytest.mark.unit


def _day(day: str) -> dict[str, object]:
    return {
        "date": day,
        "temp_min": 10.0,
        "temp_max": 15.0,
        "temp_avg": 12.0,
        "condition": "cloudy",
        "icon": "04d",
        "weather_main": "Clouds",
        "humidity_avg": 70,
        "wind_speed_avg": 2.0,
    }


def _client(start: date, count: int) -> AsyncMock:
    client = AsyncMock()
    daily = [_day((start + timedelta(days=i)).isoformat()) for i in range(count)]
    client.get_daily_forecast = AsyncMock(
        return_value={"daily": daily, "city": {"name": "Montbéliard", "country": "FR"}}
    )
    return client


async def _run(client: AsyncMock, **kwargs: object) -> dict[str, object]:
    with (
        patch.object(
            weather_tools,
            "_geocode_with_city_fallback",
            new=AsyncMock(return_value=(47.51, 6.80, "Montbéliard", "FR")),
        ),
        patch.object(weather_tools, "attach_environment_extras", new=AsyncMock()),
        patch.object(
            weather_tools,
            "_person_timezone_and_language",
            new=AsyncMock(return_value=("UTC", "en")),
        ),
    ):
        return await _get_weather_forecast_tool_impl.execute_api_call(
            client, uuid4(), location="Montbéliard", runtime=None, units="metric", **kwargs
        )


class TestForecastWindowDays:
    def test_omitted_count_with_a_date_is_that_day(self) -> None:
        assert forecast_window_days(None, is_specific_date=True, max_days=5) == 1

    def test_omitted_count_without_a_date_is_the_whole_window(self) -> None:
        assert forecast_window_days(None, is_specific_date=False, max_days=5) == 5

    def test_an_explicit_count_equal_to_the_default_is_honoured(self) -> None:
        assert forecast_window_days(5, is_specific_date=True, max_days=5) == 5

    @pytest.mark.parametrize(("requested", "expected"), [(0, 1), (-3, 1), (99, 5), (3, 3)])
    def test_an_explicit_count_is_bounded(self, requested: int, expected: int) -> None:
        assert forecast_window_days(requested, is_specific_date=False, max_days=5) == expected


class TestExecute:
    async def test_next_days_from_today_returns_every_day_asked(self) -> None:
        window = get_settings().weather_forecast_max_days
        today = datetime.now(UTC).date()
        client = _client(today, window)
        result = await _run(client, date=today.isoformat(), days=window)
        assert result["success"] is True
        data = result["data"]
        assert isinstance(data, dict)
        assert data["forecast_days"] == window
        assert data["requested_days"] == window
        assert client.get_daily_forecast.await_args.kwargs["days"] == window

    async def test_a_specific_date_without_count_returns_that_day(self) -> None:
        today = datetime.now(UTC).date()
        target = today + timedelta(days=1)
        result = await _run(
            _client(today, get_settings().weather_forecast_max_days), date=target.isoformat()
        )
        data = result["data"]
        assert isinstance(data, dict)
        assert [day["date"] for day in data["daily"]] == [target.isoformat()]
        assert data["requested_days"] == 1

    async def test_a_window_cut_by_the_horizon_states_the_count_asked(self) -> None:
        window = get_settings().weather_forecast_max_days
        today = datetime.now(UTC).date()
        start = today + timedelta(days=window - 2)
        result = await _run(_client(today, window), date=start.isoformat(), days=window)
        data = result["data"]
        assert isinstance(data, dict)
        assert data["forecast_days"] == 2
        assert data["requested_days"] == window

    async def test_a_count_beyond_the_window_is_bounded_and_stated(self) -> None:
        window = get_settings().weather_forecast_max_days
        today = datetime.now(UTC).date()
        result = await _run(_client(today, window), days=window + 10)
        data = result["data"]
        assert isinstance(data, dict)
        assert data["forecast_days"] == window
        assert data["requested_days"] == window + 10

    async def test_the_first_day_past_the_horizon_is_refused(self) -> None:
        past = datetime.now(UTC).date() + timedelta(days=get_settings().weather_forecast_max_days)
        client = AsyncMock()
        result = await _run(client, date=past.isoformat())
        assert result["success"] is False
        assert result["error"] == "date_beyond_forecast"
        client.get_daily_forecast.assert_not_awaited()

    async def test_a_date_the_provider_did_not_cover_is_refused_not_replaced(self) -> None:
        today = datetime.now(UTC).date()
        result = await _run(_client(today + timedelta(days=1), 3), date=today.isoformat())
        assert result["success"] is False
        assert result["error"] == "no_forecast_for_date"
        assert today.isoformat() in str(result["message"])

    async def test_an_empty_provider_answer_is_refused_not_a_silent_success(self) -> None:
        result = await _run(_client(datetime.now(UTC).date(), 0))
        assert result["success"] is False
        assert result["error"] == "no_forecast_for_date"


class TestPublishedContract:
    def test_manifest_and_react_schema_read_one_text(self) -> None:
        # The ReAct loop binds the tool's own schema, the planner reads the manifest (ADR-310).
        field = weather_tools.get_weather_forecast_tool.args_schema.model_fields["days"]
        assert field.description is not None
        assert field.description.startswith(FORECAST_DAYS_DESCRIPTION)
        assert _DAYS_PARAM.description == FORECAST_DAYS_DESCRIPTION
        assert field.default is None

    def test_the_published_bounds_are_the_enforced_ones(self) -> None:
        window = get_settings().weather_forecast_max_days
        assert {c.kind: c.value for c in _DAYS_PARAM.constraints} == {
            "minimum": 1,
            "maximum": window,
        }
        assert str(window) in FORECAST_DAYS_DESCRIPTION


async def test_a_cut_window_reaches_the_model_with_the_count_asked() -> None:
    window = get_settings().weather_forecast_max_days
    today = datetime.now(UTC).date()
    result = await _run(
        _client(today, window), date=(today + timedelta(days=window - 2)).isoformat(), days=window
    )
    output = _get_weather_forecast_tool_impl.format_registry_response(result)
    assert output.structured_data["days"] == 2
    assert output.structured_data["requested_days"] == window
