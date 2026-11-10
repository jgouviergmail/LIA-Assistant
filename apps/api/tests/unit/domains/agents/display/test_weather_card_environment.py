"""WeatherCard AQ/pollen enrichment rendering (2026-08).

The card already had a dormant AQI slot (assuming the EPA scale). Google's
universal index is INVERTED (100 = excellent), so when the enrichment ships
its own localized category, the card must show THAT wording and never
re-derive a label from the number.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.weather_card import WeatherCard

pytestmark = pytest.mark.unit


def _ctx() -> RenderContext:
    return RenderContext(viewport="desktop", language="fr", timezone="Europe/Paris")


class TestAirQualityRendering:
    def test_api_category_wins_over_the_epa_label(self) -> None:
        html = WeatherCard().render(
            {
                "temperature": "21°C",
                "description": "ciel dégagé",
                "aqi": 71,
                "aqi_category": "Bonne qualité de l'air",
            },
            _ctx(),
            with_wrapper=False,
        )
        # The apostrophe is HTML-escaped by the card (XSS boundary).
        assert "Bonne qualité de l&#x27;air" in html
        # 71 on the EPA scale would read "Modéré" — the inverted UAQI must
        # never be labeled through the EPA table.
        assert "Modéré" not in html

    def test_category_without_a_number_still_renders(self) -> None:
        # MEASURED in prod: the French national index has a category and NO
        # number. Gating the row on the number hid the whole air-quality
        # signal for every French user.
        html = WeatherCard().render(
            {
                "temperature": "21°C",
                "description": "ciel dégagé",
                "aqi": None,
                "aqi_category": "Moyen",
                "aqi_label": "IQA (FR)",
                "has_air_quality": True,
            },
            _ctx(),
            with_wrapper=False,
        )
        assert "Moyen" in html
        assert "IQA (FR)" in html
        # No fabricated number, and no empty parentheses either.
        assert "()" not in html
        assert "None" not in html

    def test_value_and_label_render_together_when_both_exist(self) -> None:
        html = WeatherCard().render(
            {
                "temperature": "21°C",
                "description": "ciel dégagé",
                "aqi": 66,
                "aqi_category": "Bonne qualité de l&#x27;air",
                "aqi_label": "Universal AQI",
                "has_air_quality": True,
            },
            _ctx(),
            with_wrapper=False,
        )
        assert "66" in html
        assert "Universal AQI" in html

    def test_legacy_numeric_aqi_keeps_the_epa_label(self) -> None:
        html = WeatherCard().render(
            {"temperature": "21°C", "description": "ciel dégagé", "aqi": 42},
            _ctx(),
            with_wrapper=False,
        )
        assert "Bon" in html


class TestForecastCardRendering:
    def test_forecast_card_shows_the_environment_line(self) -> None:
        # "Il fait quoi cette semaine ?" — the air-quality/pollen signal of
        # TODAY is what decides an outdoor plan, so the multi-day strip
        # carries it too (the enrichment is cached, so it costs nothing extra).
        html = WeatherCard().render(
            {
                "type": "forecast",
                "forecasts": [
                    {"date": "2026-08-22", "temp_max": "24°C", "temp_min": "14°C"},
                    {"date": "2026-08-23", "temp_max": "26°C", "temp_min": "15°C"},
                ],
                "aqi_category": "Moyen",
                "aqi_label": "IQA (FR)",
                "has_air_quality": True,
                "pollen": [{"name": "Graminées", "category": "Élevé", "index": 4}],
            },
            _ctx(),
            with_wrapper=False,
        )
        assert "Moyen" in html
        assert "Graminées" in html

    def test_forecast_card_without_enrichment_is_unchanged(self) -> None:
        html = WeatherCard().render(
            {
                "type": "forecast",
                "forecasts": [{"date": "2026-08-22", "temp_max": "24°C", "temp_min": "14°C"}],
            },
            _ctx(),
            with_wrapper=False,
        )
        assert "Pollen" not in html
        assert "Qualité de l" not in html


class TestPollenRendering:
    def test_in_season_pollen_lines_are_rendered(self) -> None:
        html = WeatherCard().render(
            {
                "temperature": "21°C",
                "description": "ciel dégagé",
                "pollen": [
                    {"name": "Graminées", "category": "Élevé", "index": 4},
                    {"name": "Ambroisie", "category": "Modéré", "index": 2},
                ],
            },
            _ctx(),
            with_wrapper=False,
        )
        assert "Pollen" in html
        assert "Graminées" in html
        assert "Élevé" in html
        assert "Ambroisie" in html

    def test_no_pollen_data_renders_nothing(self) -> None:
        html = WeatherCard().render(
            {"temperature": "21°C", "description": "ciel dégagé"},
            _ctx(),
            with_wrapper=False,
        )
        assert "Pollen" not in html


def _render_soup(data: dict[str, object], language: str) -> BeautifulSoup:
    return BeautifulSoup(
        WeatherCard().render(data, RenderContext(language=language), with_wrapper=False),
        "html.parser",
    )


@pytest.mark.parametrize("language", ["fr", "en", "es", "de", "it", "zh-CN"])
def test_environment_is_readable_without_opening_weather_details(language: str) -> None:
    soup = _render_soup(
        {
            "temperature": "21°C",
            "pressure": "1008 hPa",
            "aqi_category": "Moyen",
            "aqi_label": "IQA (FR)",
            "pollen": [
                {"name": "Graminées", "category": "Élevé"},
                {"name": "Ambroisie", "category": "Modéré"},
            ],
        },
        language,
    )
    environment = soup.select_one(".lia-weather__environment")
    assert environment is not None
    assert environment.find_parent("details") is None
    assert V3Messages.get_air_quality(language) in environment.get_text()
    assert V3Messages.get_pollen(language) in environment.get_text()
    for supplied in ("Moyen", "IQA (FR)", "Graminées", "Élevé", "Ambroisie", "Modéré"):
        assert supplied in environment.get_text()
        assert soup.get_text().count(supplied) == 1
    details = soup.select_one("details.lia-collapsible")
    assert details is not None
    assert not details.has_attr("open")
    assert "1008 hPa" in details.get_text()
    assert details.select_one(".lia-weather__environment") is None


@pytest.mark.parametrize(
    ("payload", "expected", "absent"),
    [
        ({"aqi": 0}, "0 (Bon)", V3Messages.get_pollen("fr")),
        ({"aqi_category": "Moyen"}, "Moyen", V3Messages.get_pollen("fr")),
        (
            {"pollen": [{"name": "Graminées", "category": "Élevé"}]},
            "Graminées Élevé",
            V3Messages.get_air_quality("fr"),
        ),
        (
            {"pollen": [None, {}, {"name": "Ambroisie", "category": "Modéré"}]},
            "Ambroisie Modéré",
            V3Messages.get_air_quality("fr"),
        ),
    ],
)
def test_partial_environment_keeps_each_supplied_signal_visible(
    payload: dict[str, object], expected: str, absent: str
) -> None:
    soup = _render_soup({"temperature": "21°C", **payload}, "fr")
    environment = soup.select_one(".lia-weather__environment")
    assert environment is not None
    assert expected in environment.get_text()
    assert absent not in environment.get_text()
    assert environment.find_parent("details") is None
    assert soup.find("details") is None
    assert "None" not in environment.get_text()


@pytest.mark.parametrize("pollen", [None, [], {}, "missing", [None, {}]])
def test_missing_environment_does_not_leave_an_empty_panel(pollen: object) -> None:
    soup = _render_soup(
        {"temperature": "21°C", "aqi": None, "has_air_quality": True, "pollen": pollen},
        "fr",
    )
    assert soup.select_one(".lia-weather__environment") is None
    assert soup.find("details") is None


def test_environment_text_remains_literal_after_becoming_immediately_visible() -> None:
    category = '<script>alert("category")</script>'
    index_label = "Local <b>scale</b>"
    pollen_name = '<img src=x onerror="alert(1)">'
    pollen_category = "Low & falling"
    soup = _render_soup(
        {
            "aqi_category": category,
            "aqi_label": index_label,
            "pollen": [{"name": pollen_name, "category": pollen_category}],
        },
        "en",
    )
    environment = soup.select_one(".lia-weather__environment")
    assert environment is not None
    for supplied in (category, index_label, pollen_name, pollen_category):
        assert supplied in environment.get_text()
    assert not environment.select("script, img, b")


@pytest.mark.parametrize(("kind", "collection"), [("forecast", "forecasts"), ("hourly", "hourly")])
def test_series_environment_is_visible_without_opening_a_forecast_slot(
    kind: str, collection: str
) -> None:
    soup = _render_soup(
        {
            "type": kind,
            collection: [{"date": "2026-11-08", "temp_min": 10, "temp_max": 20, "temp": 15}],
            "aqi_category": "Global air reading",
            "pollen": [{"name": "Global pollen reading", "category": "Low"}],
        },
        "en",
    )
    environments = soup.select(".lia-weather__environment")
    assert len(environments) == 1
    environment = environments[0]
    assert environment.find_parent("details") is None
    for supplied in ("Global air reading", "Global pollen reading"):
        assert supplied in environment.get_text()
        assert soup.get_text().count(supplied) == 1


@pytest.mark.parametrize(("kind", "collection"), [("forecast", "forecasts"), ("hourly", "hourly")])
def test_slot_environment_stays_with_its_reading_without_a_second_disclosure(
    kind: str, collection: str
) -> None:
    soup = _render_soup(
        {
            "type": kind,
            collection: [
                {
                    "date": "2026-11-08",
                    "temp": 15,
                    "temp_min": 10,
                    "temp_max": 20,
                    "pressure": "1008 hPa",
                    "aqi_category": "First reading only",
                    "pollen": [{"name": "First pollen only", "category": "Low"}],
                },
                {"date": "2026-11-09", "temp": 16, "temp_min": 11, "temp_max": 21},
            ],
        },
        "en",
    )
    slots = soup.select("details.lia-weather-slot")
    assert len(slots) == 2
    environment = slots[0].select_one(".lia-weather__environment")
    assert environment is not None
    assert environment.find_parent("details") is slots[0]
    assert "First reading only" in environment.get_text()
    assert "First pollen only" in environment.get_text()
    assert slots[1].select_one(".lia-weather__environment") is None
    assert len(soup.select(".lia-weather__environment")) == 1
    details = slots[0].select_one("details.lia-collapsible")
    assert details is not None
    assert not details.has_attr("open")
    assert "1008 hPa" in details.get_text()
