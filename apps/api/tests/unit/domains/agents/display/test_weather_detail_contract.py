"""Real weather projection, registry persistence and accessible presentation."""

import json
from datetime import UTC, datetime

import pytest
from bs4 import BeautifulSoup

from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.weather_card import WeatherCard
from src.domains.agents.tools.weather_formatting import _format_hourly_response
from src.domains.agents.tools.weather_tools import _get_hourly_forecast_tool_impl

pytestmark = pytest.mark.unit


def weather_slots():
    return {
        "city": {"name": "Lyon", "country": "FR"},
        "list": [
            {
                "dt": int(datetime(2026, 10, 3, hour, tzinfo=UTC).timestamp()),
                "main": {"temp": 0, "feels_like": -2.5, "humidity": 0, "pressure": 1008},
                "weather": [{"description": "clear sky", "icon": "01d"}],
                "wind": {"speed": 0, "deg": 0, "gust": 2.4},
                "visibility": 0,
                "clouds": {"all": 0},
                "pop": 0,
                "rain": {"3h": 0},
                "snow": {"3h": 1.5},
            }
            for hour in (21, 0, 3)
        ],
    }


def hourly_payload():
    result = _format_hourly_response(
        weather_slots(), "Lyon", "FR", 3, "metric", user_timezone="Europe/Paris"
    )
    result["data"]["date"] = "2026-10-03"
    output = _get_hourly_forecast_tool_impl.format_registry_response(result)
    item = next(iter(output.registry_updates.values()))
    return card_payload(RegistryItem.model_validate(json.loads(item.model_dump_json())))


def test_full_supplied_slot_measurements_survive_the_real_registry_round_trip():
    slot = hourly_payload()["hourly"][0]
    assert slot["wind_direction"] == "0°"
    assert slot["wind_gust"] == "2.4 m/s"
    assert slot["pressure"] == "1008 hPa"
    assert slot["visibility"] == "0.0 km"
    assert slot["precipitation_probability"] == "0"
    assert slot["rain_amount"] == "0 mm / 3 h"
    assert slot["snow_amount"] == "1.5 mm / 3 h"


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_every_slot_has_a_named_native_selector_full_details_and_comparison(language):
    soup = BeautifulSoup(
        WeatherCard().render(hourly_payload(), RenderContext(language=language)), "html.parser"
    )
    selectors = soup.select("details.lia-weather-slot > summary")
    assert len(selectors) == 3
    assert len({selector.get_text() for selector in selectors}) == 3
    assert "1008 hPa" in soup.get_text()
    assert "2.4 m/s" in soup.get_text()
    assert "1.5 mm / 3 h" in soup.get_text()
    assert soup.select_one("table caption")
    assert len(soup.select("table tbody tr")) == 3


def test_all_received_days_are_reachable_beyond_the_initial_view_limit():
    data = {
        "type": "forecast",
        "location": "Lyon",
        "forecasts": [
            {
                "date": f"2026-10-{day:02d}",
                "temp_min": 0,
                "temp_max": 2,
                "humidity": "0%",
                "wind_speed": "0 m/s",
                "description": "clear",
            }
            for day in range(3, 13)
        ],
    }
    soup = BeautifulSoup(WeatherCard().render(data, RenderContext(language="en")), "html.parser")
    assert len(soup.select("details.lia-weather-slot")) == 10
    assert "0°C" in soup.get_text()


@pytest.mark.parametrize("value", [None, {}, True, "PRIVATE_RAW_TREE", [None]])
def test_malformed_hourly_collections_never_dump_raw_trees_or_raise(value):
    result = _format_hourly_response({"city": {}, "list": value}, "Lyon", "FR", 3, "metric")
    assert result["data"]["hourly"] == []


def test_north_zero_and_zero_pressure_remain_real_current_measurements():
    card = WeatherCard()
    assert card._format_wind_direction(0, "en") == "N"
    assert (
        "Pressure"
        in BeautifulSoup(
            card.render({"location": "Lyon", "pressure": 0}, RenderContext(language="en")),
            "html.parser",
        ).get_text()
    )


def test_missing_daily_measurements_are_not_averaged_as_zero():
    from src.domains.connectors.clients.weather_normalization import aggregate_daily_forecast

    raw = weather_slots()
    raw["list"] = [
        raw["list"][0],
        {"dt": raw["list"][0]["dt"], "main": {}, "wind": {}, "weather": []},
    ]
    raw["list"][0]["main"].update({"temp": 10, "humidity": 80})
    raw["list"][0]["wind"]["speed"] = 4
    day = aggregate_daily_forecast(raw, 1, "Europe/Paris")["daily"][0]
    assert day["temp_min"] == day["temp_max"] == day["temp_avg"] == 10
    assert day["humidity_avg"] == 80
    assert day["wind_speed_avg"] == 4


def test_legacy_temperature_range_does_not_change_fahrenheit_to_celsius():
    assert WeatherCard()._format_temperature({"min": "32°F", "max": "50°F"}) == "41°F"


@pytest.mark.parametrize("multi", [False, True])
def test_actual_daily_registry_items_form_one_selectable_series_in_both_display_paths(multi):
    from src.domains.agents.display.config import DisplayConfig
    from src.domains.agents.display.html_renderer import HtmlRenderer
    from src.domains.agents.tools.weather_formatting import _format_forecast_response
    from src.domains.agents.tools.weather_tools import _get_weather_forecast_tool_impl

    result = _format_forecast_response(
        [
            {
                "date": f"2026-10-{day:02d}",
                "temp_min": 0,
                "temp_max": 5,
                "temp_avg": 2,
                "condition": "clear sky",
                "humidity_avg": 0,
                "wind_speed_avg": 0,
            }
            for day in range(3, 6)
        ],
        "Lyon",
        "FR",
        3,
        "metric",
        "2026-10-03",
    )
    output = _get_weather_forecast_tool_impl.format_registry_response(result)
    items = [
        card_payload(RegistryItem.model_validate_json(item.model_dump_json()))
        for item in output.registry_updates.values()
    ]
    renderer = HtmlRenderer()
    config = DisplayConfig(language="en", timezone="Europe/Paris")
    markup = (
        renderer.render_multi({"weathers": {"weathers": items}}, config)
        if multi
        else renderer.render("weathers", {"weathers": items}, config)
    )
    soup = BeautifulSoup(markup, "html.parser")
    assert len(soup.select(".lia-card.lia-weather")) == 1
    assert len(soup.select(".lia-weather-slot")) == 3


def test_forecast_series_never_combines_different_locations_or_current_readings():
    from src.domains.agents.display.config import DisplayConfig
    from src.domains.agents.display.html_renderer import HtmlRenderer

    items = [
        {"type": "forecast", "date": "2026-10-03", "location": "Lyon", "temp_max": "2°C"},
        {"type": "forecast", "date": "2026-10-04", "location": "Paris", "temp_max": "3°C"},
        {"type": "current", "location": "Lyon", "temperature": "1°C"},
    ]
    soup = BeautifulSoup(
        HtmlRenderer().render("weathers", {"weathers": items}, DisplayConfig(language="en")),
        "html.parser",
    )
    assert len(soup.select(".lia-card.lia-weather")) == 3


def test_utc_text_fallback_is_projected_before_target_day_filtering():
    from src.domains.agents.tools.weather_formatting import _entry_local_date

    raw = {"dt_txt": "2026-10-03 23:00:00", "main": {"temp": 0}}
    assert _entry_local_date(raw, "Europe/Paris") == "2026-10-04"
    result = _format_hourly_response(
        {"list": [raw]},
        "Lyon",
        "FR",
        1,
        "metric",
        target_date="2026-10-04",
        user_timezone="Europe/Paris",
    )
    assert result["data"]["hourly"][0]["datetime_text"] == "2026-10-04 01:00:00"


@pytest.mark.parametrize("value", [{"PRIVATE_RAW_TREE": "secret"}, [], True, "bad"])
def test_malformed_source_time_is_not_exposed_as_a_clock(value):
    result = _format_hourly_response(
        {"list": [{"dt_txt": value, "main": {"temp": 0}}]}, "Lyon", "FR", 1, "metric"
    )
    assert result["data"]["hourly"][0]["datetime_text"] == ""


def test_actual_weather_context_keeps_new_fields_through_a_strict_json_round_trip():
    from src.domains.agents.tools.weather_tools import WeatherForecastItem

    context = WeatherForecastItem.model_validate(hourly_payload())
    restored = WeatherForecastItem.model_validate_json(context.model_dump_json())
    assert restored.hourly[0]["wind_gust"] == "2.4 m/s"
    assert restored.timezone == "Europe/Paris"
    with pytest.raises(ValueError):
        WeatherForecastItem.model_validate({"location": "Lyon", "uv_index": True})


@pytest.mark.parametrize("value", ["NaN", "Infinity", -1, True, {"PRIVATE_RAW_TREE": "secret"}])
def test_invalid_uv_readings_do_not_claim_a_health_risk(value):
    markup = WeatherCard().render(
        {"location": "Lyon", "uv_index": value}, RenderContext(language="en")
    )
    text = BeautifulSoup(markup, "html.parser").get_text()
    assert "UV" not in text
    assert "Extreme" not in text
    assert "PRIVATE_RAW_TREE" not in text


def test_source_night_icon_is_used_independently_of_the_readers_clock():
    card = WeatherCard()
    data = {"location": "Lyon", "description": "clear sky", "icon": "01n", "temperature": "0°C"}
    assert "dark_mode" in card.render(data, RenderContext(language="en"))
    assert "dark_mode" in card.render(
        {"type": "hourly", "location": "Lyon", "hourly": [data]}, RenderContext(language="en")
    )
