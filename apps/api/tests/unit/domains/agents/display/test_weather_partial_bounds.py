"""Known temperature bounds remain readable when the other bound is absent."""

import pytest

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.weather_card import WeatherCard

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("forecast", [False, True])
@pytest.mark.parametrize(
    ("bound", "value", "expected"),
    [("temp_min", "0°C", "0°C / —"), ("temp_max", "68°F", "— / 68°F")],
)
def test_single_received_bound_keeps_its_position(
    forecast: bool, bound: str, value: str, expected: str
) -> None:
    reading = {"temperature": "10°C", bound: value, "date": "2026-11-08"}
    data = {"type": "forecast", "forecasts": [reading]} if forecast else reading
    html = WeatherCard().render(data, RenderContext(language="fr"), with_wrapper=False)
    assert expected in html


def test_forecast_range_is_literal_received_text() -> None:
    html = WeatherCard().render(
        {
            "type": "forecast",
            "forecasts": [
                {
                    "date": "2026-11-08",
                    "temp_min": "1<script>unsafe()</script>",
                    "temp_max": "2°C",
                }
            ],
        },
        RenderContext(language="fr"),
        with_wrapper=False,
    )
    assert "<script>" not in html
    assert "&lt;script&gt;unsafe()&lt;/script&gt;" in html
