"""Behavioral tests for WeatherCard (43.4% covered).

WeatherCard turns OpenWeatherMap payloads into the current/forecast/hourly
cards. The value is in its pure normalisation helpers — temperature parsing
(dict vs string vs units), wind-direction cardinalisation, and the localized
UV/AQI bands — which decide the NUMBER the user reads. A rounding or band-edge
regression there is a wrong answer with no error.
"""

import pytest

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.weather_card import WeatherCard

pytestmark = pytest.mark.unit


@pytest.fixture
def card() -> WeatherCard:
    return WeatherCard()


@pytest.fixture
def ctx() -> RenderContext:
    return RenderContext(language="fr")


# ============================================================================
# TEMPERATURE FORMATTING
# ============================================================================


class TestFormatTemperature:
    """Provider temps arrive as strings, dicts, or bare numbers."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("12.4°C", "12°C"),
            ("13.6°C", "14°C"),
            ("-0.7°C", "-1°C"),
            ("20", "20°C"),
            ("18,6°C", "19°C"),  # comma decimal (fr locale from provider)
            (21, "21°C"),
        ],
    )
    def test_scalar_temperatures_are_rounded_with_unit(
        self, card: WeatherCard, raw: object, expected: str
    ) -> None:
        assert card._format_temperature(raw) == expected

    def test_half_values_use_pythons_banker_rounding(self, card: WeatherCard) -> None:
        """Documented behaviour: ``round`` ties to the even integer, so 12.5 -> 12
        and 13.5 -> 14. Not a bug, but pinned so a future switch to round-half-up
        is a deliberate, visible change rather than an accident."""
        assert card._format_temperature("12.5°C") == "12°C"
        assert card._format_temperature("13.5°C") == "14°C"

    def test_dict_with_avg_uses_avg(self, card: WeatherCard) -> None:
        assert card._format_temperature({"avg": "10.4°C", "min": "5°C", "max": "15°C"}) == "10°C"

    def test_dict_with_min_max_computes_the_average(self, card: WeatherCard) -> None:
        assert card._format_temperature({"min": "-0.7°C", "max": "1.3°C"}) == "0°C"

    def test_dict_with_only_max_falls_back_to_max(self, card: WeatherCard) -> None:
        assert card._format_temperature({"max": "15°C"}) == "15°C"

    def test_empty_temperature_is_blank(self, card: WeatherCard) -> None:
        assert card._format_temperature("") == ""
        assert card._format_temperature(None) == ""
        assert card._format_temperature({}) == ""

    def test_non_numeric_string_is_returned_as_is(self, card: WeatherCard) -> None:
        assert card._format_temperature("N/A") == "N/A"

    def test_fahrenheit_unit_is_preserved(self, card: WeatherCard) -> None:
        assert card._format_temperature("68.6°F") == "69°F"


class TestExtractNumericTemp:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("12.5°C", 12.5), ("-3°C", -3.0), ("18,6", 18.6), ("21", 21.0)],
    )
    def test_extracts_the_numeric_value(self, card: WeatherCard, raw: str, expected: float) -> None:
        assert card._extract_numeric_temp(raw) == expected

    @pytest.mark.parametrize("raw", ["", None, "N/A"])
    def test_unparsable_returns_none(self, card: WeatherCard, raw: str | None) -> None:
        assert card._extract_numeric_temp(raw) is None


# ============================================================================
# WIND DIRECTION
# ============================================================================


class TestWindDirection:
    @pytest.mark.parametrize(
        ("angle", "cardinal"),
        [
            (0, "N"),
            (45, "NE"),
            (90, "E"),
            (135, "SE"),
            (180, "S"),
            (225, "SO"),
            (270, "O"),
            (315, "NO"),
            (360, "N"),
            (22, "N"),
            (23, "NE"),
        ],
    )
    def test_angle_maps_to_cardinal(self, card: WeatherCard, angle: float, cardinal: str) -> None:
        assert card._angle_to_cardinal(angle) == cardinal

    def test_angle_is_normalised_modulo_360(self, card: WeatherCard) -> None:
        assert card._angle_to_cardinal(450) == card._angle_to_cardinal(90)

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("180°", "S"), ("180", "S"), ("270", "O")],
    )
    def test_degree_strings_become_cardinal(
        self, card: WeatherCard, raw: str, expected: str
    ) -> None:
        assert card._format_wind_direction(raw) == expected

    def test_already_cardinal_is_kept(self, card: WeatherCard) -> None:
        assert card._format_wind_direction("NO") == "NO"

    def test_empty_direction_is_blank(self, card: WeatherCard) -> None:
        assert card._format_wind_direction("") == ""
        assert card._format_wind_direction(None) == ""


# ============================================================================
# WEATHER VISUAL
# ============================================================================


class TestWeatherVisual:
    def test_known_description_maps_to_an_icon_and_class(self, card: WeatherCard) -> None:
        icon_name, css_class = card._get_weather_visual("clear")
        assert icon_name
        assert css_class != "default"

    def test_partial_match_is_accepted(self, card: WeatherCard) -> None:
        icon_name, _css = card._get_weather_visual("light rain showers")
        assert icon_name

    def test_unknown_description_falls_back_to_default(self, card: WeatherCard) -> None:
        assert card._get_weather_visual("gravitational anomaly")[1] == "default"

    def test_empty_description_falls_back_to_default(self, card: WeatherCard) -> None:
        assert card._get_weather_visual("")[1] == "default"


# ============================================================================
# UV / AQI BANDS
# ============================================================================


class TestUvLabel:
    @pytest.mark.parametrize(
        ("uv", "fragment_fr"),
        [(1, "Faible"), (2, "Faible"), (3, "Modéré"), (5, "Modéré")],
    )
    def test_low_and_moderate_bands(self, card: WeatherCard, uv: float, fragment_fr: str) -> None:
        assert card._get_uv_label(uv, "fr") == fragment_fr

    def test_band_edges_are_inclusive(self, card: WeatherCard) -> None:
        """A UV of exactly 2 is 'Faible', 2.1 is not."""
        assert card._get_uv_label(2, "fr") == "Faible"
        assert card._get_uv_label(2.1, "fr") != "Faible"

    def test_unknown_language_falls_back_to_english(self, card: WeatherCard) -> None:
        assert card._get_uv_label(1, "pt") == "Low"

    @pytest.mark.parametrize("bad", ["N/A", None, ""])
    def test_unparsable_uv_is_blank(self, card: WeatherCard, bad: object) -> None:
        assert card._get_uv_label(bad, "fr") == ""


class TestAqiLabel:
    @pytest.mark.parametrize(
        ("aqi", "expected_fr"),
        [
            (10, "Bon"),
            (50, "Bon"),
            (75, "Modéré"),
            (120, "Mauvais pour sensibles"),
            (180, "Mauvais"),
            (250, "Très mauvais"),
            (400, "Dangereux"),
        ],
    )
    def test_every_band(self, card: WeatherCard, aqi: int, expected_fr: str) -> None:
        assert card._get_aqi_label(aqi, "fr") == expected_fr

    def test_band_edge_is_inclusive(self, card: WeatherCard) -> None:
        assert card._get_aqi_label(50, "fr") == "Bon"
        assert card._get_aqi_label(51, "fr") == "Modéré"

    def test_chinese_uses_the_backend_canonical_table(self, card: WeatherCard) -> None:
        assert card._get_aqi_label(10, "zh-CN") == "良好"

    @pytest.mark.parametrize("bad", ["N/A", None])
    def test_unparsable_aqi_is_blank(self, card: WeatherCard, bad: object) -> None:
        assert card._get_aqi_label(bad, "fr") == ""


# ============================================================================
# RENDER DISPATCH
# ============================================================================


class TestRenderDispatch:
    def test_current_weather_renders(self, card: WeatherCard, ctx: RenderContext) -> None:
        html = card.render(
            {"type": "current", "location": "Paris", "temperature": "12°C", "description": "clear"},
            ctx,
        )
        assert "Paris" in html
        assert "12°C" in html

    def test_forecast_renders_each_day(self, card: WeatherCard, ctx: RenderContext) -> None:
        html = card.render(
            {
                "type": "forecast",
                "location": "Paris",
                "forecasts": [
                    {
                        "date": "2026-07-20",
                        "temp": {"min": "10°C", "max": "20°C"},
                        "description": "clear",
                    },
                    {
                        "date": "2026-07-21",
                        "temp": {"min": "12°C", "max": "22°C"},
                        "description": "rain",
                    },
                ],
            },
            ctx,
        )
        assert isinstance(html, str)
        assert "lia" in html

    def test_hourly_renders(self, card: WeatherCard, ctx: RenderContext) -> None:
        html = card.render(
            {
                "type": "hourly",
                "location": "Paris",
                "hourly": [{"time": "14:00", "temp": "18°C", "description": "clear"}],
            },
            ctx,
        )
        assert isinstance(html, str)

    def test_unknown_type_falls_back_to_current(
        self, card: WeatherCard, ctx: RenderContext
    ) -> None:
        html = card.render({"type": "martian", "location": "Paris", "temperature": "12°C"}, ctx)
        assert "Paris" in html

    def test_location_is_escaped(self, card: WeatherCard, ctx: RenderContext) -> None:
        html = card.render(
            {"type": "current", "location": "<script>alert(1)</script>", "temperature": "12°C"}, ctx
        )
        assert "<script>alert" not in html
