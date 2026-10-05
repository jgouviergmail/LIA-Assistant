"""Provider conditions survive projection and drive the visible weather glyph."""

from datetime import UTC, datetime

import pytest
from bs4 import BeautifulSoup

from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.weather_card import WeatherCard
from src.domains.agents.tools.weather_formatting import (
    _format_current_weather_response,
    _format_forecast_response,
    _format_hourly_response,
)
from src.domains.agents.tools.weather_schemas import WeatherForecastItem
from src.domains.agents.tools.weather_tools import (
    _get_current_weather_tool_impl,
    _get_hourly_forecast_tool_impl,
    _get_weather_forecast_tool_impl,
)
from src.domains.connectors.clients.google_weather_client import _condition_entry
from src.domains.connectors.clients.weather_normalization import aggregate_daily_forecast

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("kind", ["current", "forecast", "hourly"])
@pytest.mark.parametrize(
    ("code", "glyph"),
    [
        ("01d", "light_mode"),
        ("01n", "dark_mode"),
        ("02d", "partly_cloudy_day"),
        ("02n", "partly_cloudy_night"),
        ("03d", "cloud"),
        ("03n", "cloud"),
        ("04d", "cloud"),
        ("04n", "cloud"),
        ("09d", "rainy"),
        ("09n", "rainy"),
        ("10d", "rainy"),
        ("10n", "rainy"),
        ("11d", "thunderstorm"),
        ("11n", "thunderstorm"),
        ("13d", "ac_unit"),
        ("13n", "ac_unit"),
        ("50d", "foggy"),
        ("50n", "foggy"),
    ],
)
def test_provider_code_drives_current_and_every_forecast_icon(kind: str, code: str, glyph: str):
    # Deliberately contradictory text catches a renderer that guesses from prose.
    reading = {"date": "2026-10-04", "description": "clear sky", "icon": code}
    data = {"location": "Lyon", "type": kind, **reading}
    if kind != "current":
        data["hourly" if kind == "hourly" else "forecasts"] = [reading]
    soup = BeautifulSoup(WeatherCard().render(data, RenderContext(language="de")), "html.parser")
    icons = soup.select(
        ".lia-weather__icon .material-symbols-outlined, "
        ".lia-weather-slot__icon .material-symbols-outlined"
    )
    assert icons
    assert {symbol.get_text() for symbol in icons} == {glyph}


@pytest.mark.parametrize("kind", ["current", "hourly"])
@pytest.mark.parametrize(
    ("condition", "description", "glyph"),
    [
        ("RAIN", "lluvia", "rainy"),
        ("SNOW", "Schnee", "ac_unit"),
        ("THUNDERSTORM", "雷暴", "thunderstorm"),
        ("WINDY", "ventoso", "air"),
        ("FOG", "brouillard", "foggy"),
    ],
)
def test_google_localized_condition_survives_real_registry_round_trip(
    kind: str, condition: str, description: str, glyph: str
):
    raw = {
        "dt": int(datetime(2026, 10, 4, 12, tzinfo=UTC).timestamp()),
        "main": {"temp": 10},
        "weather": [
            _condition_entry(
                {"weatherCondition": {"type": condition, "description": {"text": description}}}
            )
        ],
        "source": "google_weather",
    }
    if kind == "current":
        result = _format_current_weather_response(raw, "Lyon", "FR", 45.75, 4.85, "metric")
        output = _get_current_weather_tool_impl.format_registry_response(result)
    else:
        result = _format_hourly_response({"list": [raw]}, "Lyon", "FR", 1, "metric")
        output = _get_hourly_forecast_tool_impl.format_registry_response(result)
    stored = next(iter(output.registry_updates.values()))
    restored = RegistryItem.model_validate_json(stored.model_dump_json())
    context = WeatherForecastItem.model_validate(card_payload(restored))
    soup = BeautifulSoup(
        WeatherCard().render(
            context.model_dump(), RenderContext(language="en", timezone="Pacific/Honolulu")
        ),
        "html.parser",
    )
    symbol = soup.select_one(".lia-weather__icon .material-symbols-outlined")
    assert symbol is not None and symbol.get_text() == glyph
    assert description in soup.get_text()


def test_daily_description_and_icon_stay_paired_through_aggregation_and_registry():
    # An overnight minority must not supply the daily glyph. A secondary weather
    # object is also not the primary condition for any slot (OWM's contract).
    slots = []
    for hour, code, description in [
        (0, "01n", "klar"),
        (9, "13d", "Schnee"),
        (15, "13d", "Schnee"),
    ]:
        slots.append(
            {
                "dt": int(datetime(2026, 10, 4, hour, tzinfo=UTC).timestamp()),
                "main": {"temp": 2},
                "weather": [
                    {"description": description, "icon": code, "main": "Snow" if hour else "Clear"},
                    {"description": "Regen", "icon": "10d", "main": "Rain"},
                ],
            }
        )
    day = aggregate_daily_forecast({"list": slots}, 1, "Europe/Paris")["daily"][0]
    result = _format_forecast_response([day], "Lyon", "FR", 1, "metric", "2026-10-04")
    output = _get_weather_forecast_tool_impl.format_registry_response(result)
    stored = next(iter(output.registry_updates.values()))
    restored = RegistryItem.model_validate_json(stored.model_dump_json())
    context = WeatherForecastItem.model_validate(card_payload(restored))
    assert context.icon == "13d"
    assert context.description == "Schnee"
    soup = BeautifulSoup(
        WeatherCard().render(context.model_dump(), RenderContext(language="de")), "html.parser"
    )
    symbol = soup.select_one(".lia-weather__icon .material-symbols-outlined")
    assert symbol is not None and symbol.get_text() == "ac_unit"


@pytest.mark.parametrize(
    ("description", "glyph"),
    [
        ("thunderstorm with light drizzle", "thunderstorm"),
        ("light rain and snow", "ac_unit"),
        ("orage avec pluie", "thunderstorm"),
        ("freezing rain", "ac_unit"),
        ("clear night", "dark_mode"),
        ("snowstorm", "ac_unit"),
    ],
)
def test_legacy_compound_description_never_hides_the_storm_snow_or_night(
    description: str, glyph: str
):
    soup = BeautifulSoup(
        WeatherCard().render({"description": description}, RenderContext(language="en")),
        "html.parser",
    )
    symbol = soup.select_one(".lia-weather__icon .material-symbols-outlined")
    assert symbol is not None and symbol.get_text() == glyph


def test_daily_summary_prefers_daytime_for_the_same_dominant_condition():
    slots = [
        {
            "dt": int(datetime(2026, 10, 4, hour, tzinfo=UTC).timestamp()),
            "weather": [{"description": "晴朗", "icon": code, "main": "Clear"}],
        }
        for hour, code in [(0, "01n"), (3, "01n"), (12, "01d")]
    ]
    summary = aggregate_daily_forecast({"list": slots}, 1, "UTC")["daily"][0]
    assert summary["icon"] == "01d"


@pytest.mark.parametrize(
    ("day_type", "day_description", "code", "main", "glyph", "color_class"),
    [
        ("CLEAR", "Ensoleillé", "01d", "Clear", "light_mode", "sunny"),
        (
            "PARTLY_CLOUDY",
            "Partiellement Ensoleillé",
            "02d",
            "Clouds",
            "partly_cloudy_day",
            "partly-cloudy",
        ),
        ("SNOW", "Neige", "13d", "Snow", "ac_unit", "snowy"),
    ],
)
def test_daily_card_uses_daytime_conditions_despite_a_localized_night_majority(
    day_type, day_description, code, main, glyph, color_class
):
    slots = []
    for hour in range(0, 24, 3):
        daytime = hour in (9, 12, 15)
        slots.append(
            {
                "dt": int(datetime(2026, 10, 5, hour, tzinfo=UTC).timestamp()),
                "main": {"temp": 24 if daytime else 10},
                "weather": [
                    _condition_entry(
                        {
                            "isDaytime": daytime,
                            "weatherCondition": {
                                "type": day_type if daytime else "CLEAR",
                                "description": {"text": day_description if daytime else "Dégagé"},
                            },
                        }
                    )
                ],
            }
        )
    summary = aggregate_daily_forecast({"list": slots}, 1, "Europe/Paris")["daily"][0]
    assert summary["condition"] == day_description
    assert summary["icon"] == code
    assert summary["weather_main"] == main
    # Temperature statistics describe the whole calendar day, including night.
    assert (summary["temp_min"], summary["temp_max"]) == (10, 24)
    result = _format_forecast_response([summary], "Lyon", "FR", 1, "metric", "2026-10-05")
    stored = next(
        iter(
            _get_weather_forecast_tool_impl.format_registry_response(
                result
            ).registry_updates.values()
        )
    )
    restored = RegistryItem.model_validate_json(stored.model_dump_json())
    context = WeatherForecastItem.model_validate(card_payload(restored))
    soup = BeautifulSoup(
        WeatherCard().render(context.model_dump(), RenderContext(language="fr")), "html.parser"
    )
    symbol = soup.select_one(".lia-weather__icon .material-symbols-outlined")
    assert symbol is not None and symbol.get_text() == glyph
    assert soup.select_one(f".lia-weather--{color_class}") is not None
    assert day_description in soup.get_text()
    # Aggregation does not rewrite the source observations used by hourly cards.
    assert slots[0]["weather"][0]["icon"] == "01n"
    assert slots[0]["weather"][0]["description"] == "Dégagé"


def test_daily_daytime_selection_respects_local_midnight_and_keeps_night_only_readings():
    slots = [
        {
            "dt": int(datetime(2026, 10, day, hour, tzinfo=UTC).timestamp()),
            "weather": [{"description": description, "icon": code, "main": main}],
        }
        for day, hour, code, description, main in [
            (4, 21, "13d", "Neige", "Snow"),  # October 4, 23:00 in Europe/Paris.
            (4, 22, "01n", "Dégagé", "Clear"),  # October 5, 00:00 locally.
            (5, 1, "01n", "Dégagé", "Clear"),
            (5, 12, "02d", "Partiellement Ensoleillé", "Clouds"),
            (5, 22, "01n", "Dégagé", "Clear"),  # October 6, 00:00 locally.
        ]
    ]
    summaries = aggregate_daily_forecast({"list": slots}, 3, "Europe/Paris")["daily"]
    assert [
        (day["date"], day["condition"], day["icon"], day["weather_main"]) for day in summaries
    ] == [
        ("2026-10-04", "Neige", "13d", "Snow"),
        ("2026-10-05", "Partiellement Ensoleillé", "02d", "Clouds"),
        ("2026-10-06", "Dégagé", "01n", "Clear"),
    ]
