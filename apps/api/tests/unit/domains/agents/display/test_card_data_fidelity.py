"""The person must receive valid source data across normalization and rendering."""

import json
from html.parser import HTMLParser

import pytest

from src.core.field_names import FIELD_DISPLAY_ONLY
from src.core.i18n_v3 import V3Messages
from src.domains.agents.data_registry.card_payload import card_payload, restore_display_fields
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.place_card import PlaceCard
from src.domains.agents.display.components.task_item import TaskItem
from src.domains.agents.display.components.weather_card import WeatherCard
from src.domains.agents.display.config import DisplayConfig
from src.domains.agents.display.html_renderer import HtmlRenderer
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.places_formatting import _format_place, format_place_details
from src.domains.agents.tools.weather_formatting import _format_current_weather_response

pytestmark = pytest.mark.unit


class PlaceOutput(ToolOutputMixin):
    tool_name = "test_place_output"
    operation = "search"


class TextReader(HTMLParser):
    def __init__(self, markup: str) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.feed(markup)

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    @property
    def text(self) -> str:
        return " ".join(self.parts)


@pytest.mark.parametrize("details", [False, True])
def test_place_review_author_and_complete_text_survive_to_the_reader(details: bool) -> None:
    review_text = "An accessible terrace. " * 20 + "The lift is beside the courtyard."
    raw = {
        "id": "test-place",
        "displayName": {"text": "Terrace"},
        "reviews": [
            {
                "text": {"text": review_text},
                "rating": 4,
                "authorAttribution": {"displayName": "Alex"},
            }
        ],
    }
    formatter = format_place_details if details else _format_place
    normalized = formatter(raw, language="en")
    markup = PlaceCard().render(restore_display_fields(normalized), RenderContext(language="en"))
    text = TextReader(markup).text
    assert "Alex" in text
    assert review_text in text
    # The full review belongs to the display projection; the model keeps its preview.
    assert len(normalized["reviews"][0]["text"]) <= 200
    assert normalized[FIELD_DISPLAY_ONLY]["reviews"][0]["text"] == review_text


@pytest.mark.parametrize("temperature_key", ["temperature", "temp", "temp_day"])
def test_zero_temperature_is_a_value_not_a_missing_measurement(temperature_key: str) -> None:
    markup = WeatherCard().render(
        {temperature_key: 0, "temp_max": 12, "location": "Test", "description": "clear"},
        RenderContext(language="en"),
        with_wrapper=False,
    )
    assert "0°C" in TextReader(markup).text
    assert "12°C" not in TextReader(markup).text


@pytest.mark.parametrize(
    ("key", "label"),
    [
        ("uv_index", V3Messages.get_uv_index("en")),
        ("clouds", V3Messages.get_cloud_cover("en")),
        ("visibility", V3Messages.get_visibility("en")),
    ],
)
def test_zero_extended_measurements_remain_available(key: str, label: str) -> None:
    markup = WeatherCard().render({"temperature": 5, key: 0}, RenderContext(language="en"))
    text = TextReader(markup).text
    assert f"{label}: 0" in text


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_task_high_priority_is_visible_and_localized(language: str) -> None:
    markup = TaskItem().render(
        {"title": "Renew insurance", "priority": "high"}, RenderContext(language=language)
    )
    assert V3Messages.get_priority(language, "high") in TextReader(markup).text


def test_calendar_is_not_presented_as_an_event_and_keeps_its_timezone() -> None:
    markup = HtmlRenderer().render(
        "calendars",
        {
            "calendars": [
                {
                    "summary": "Team calendar",
                    "primary": True,
                    "time_zone": "Europe/Paris",
                    "access_role": "reader",
                }
            ]
        },
        DisplayConfig(language="en"),
    )
    text = TextReader(markup).text
    assert "Team calendar" in text
    assert "Europe/Paris" in text
    assert "Read only" in text
    assert "Primary" in text


@pytest.mark.parametrize("rating", [None, "bad", -10, 50000, float("nan"), float("inf")])
def test_incomplete_review_rating_cannot_erase_the_review_or_generate_unbounded_stars(
    rating: object,
) -> None:
    markup = PlaceCard().render(
        {
            "name": "Test",
            "reviews": [
                {"text": "Access through the courtyard.", "rating": rating},
            ],
        },
        RenderContext(language="en"),
    )
    assert "Access through the courtyard." in TextReader(markup).text
    assert len(markup) < 5000


def test_place_review_markup_is_text_and_does_not_escape_the_card() -> None:
    hostile = '<script>alert("x")</script>'
    markup = PlaceCard().render(
        {
            "name": "Test",
            "reviews": [
                {
                    "author_name": hostile,
                    "text": hostile,
                    "rating": 5,
                }
            ],
        },
        RenderContext(language="en"),
    )
    assert "<script>" not in markup
    assert hostile in TextReader(markup).text


def test_microsoft_importance_is_visible_without_inventing_a_google_priority() -> None:
    ctx = RenderContext(language="en")
    high = TaskItem().render({"title": "Renew insurance", "importance": "high"}, ctx)
    unspecified = TaskItem().render({"title": "Renew insurance"}, ctx)
    assert V3Messages.get_priority("en", "high") in TextReader(high).text
    assert V3Messages.get_priority("en", "high") not in TextReader(unspecified).text


@pytest.mark.parametrize("role", [None, {}, [], "unsupported"])
def test_unknown_calendar_access_does_not_fabricate_permissions(role: object) -> None:
    markup = HtmlRenderer().render(
        "calendars",
        {
            "calendars": [
                {"summary": "Team calendar", "access_role": role},
            ]
        },
        DisplayConfig(language="en"),
    )
    text = TextReader(markup).text
    assert "Team calendar" in text
    assert "Can edit" not in text


def test_display_review_round_trip_does_not_enlarge_the_model_payload() -> None:
    full_text = "A readable review. " * 30 + "Tail that must survive."
    normalized = _format_place(
        {
            "id": "test",
            "displayName": {"text": "Terrace"},
            "reviews": [{"text": {"text": full_text}, "rating": 4}],
        },
        language="en",
    )
    output = PlaceOutput().build_places_output([normalized])
    item = next(iter(output.registry_updates.values()))
    stored = json.loads(item.model_dump_json())
    assert full_text not in json.dumps(item.payload)
    assert full_text not in json.dumps(output.structured_data)
    projected = card_payload(stored)
    assert projected is not None
    assert full_text in TextReader(PlaceCard().render(projected, RenderContext(language="en"))).text


def test_zero_visibility_and_gust_survive_provider_normalization() -> None:
    output = _format_current_weather_response(
        {"visibility": 0, "wind": {"gust": 0}},
        "Test",
        "",
        0,
        0,
        "metric",
    )
    weather = output["data"]["weather"]
    assert weather["visibility"] == "0.0 km"
    assert weather["wind"]["gust"] == "0 m/s"


def test_missing_visibility_is_not_fabricated_as_zero() -> None:
    output = _format_current_weather_response({}, "Test", "", 0, 0, "metric")
    assert output["data"]["weather"]["visibility"] == ""
