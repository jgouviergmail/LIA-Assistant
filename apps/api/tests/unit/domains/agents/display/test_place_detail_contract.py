"""Provider fields through both tool formatters, registry projection and cards."""

import json
from collections.abc import Callable

import pytest

from src.core.field_names import FIELD_DISPLAY_ONLY
from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.place_card import PlaceCard
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.places_formatting import _format_place, format_place_details

pytestmark = pytest.mark.unit


def test_place_without_photos_retains_provider_attribution():
    markup = PlaceCard().render({"name": "Place"}, RenderContext())
    assert 'translate="no">Google Maps</span>' in markup


def test_partial_period_keeps_the_supplied_close_without_inventing_an_open():
    markup = PlaceCard().render(
        {
            "name": "Place",
            "currentOpeningHours": {
                "periods": [{"close": {"day": 1, "hour": 4, "truncated": True}}]
            },
        },
        RenderContext(language="en"),
    )
    assert "Monday 04:00" in markup
    assert "partial" in markup.lower()
    assert "00:00" not in markup


class PlaceDetailsOutput(ToolOutputMixin):
    tool_name = "place_detail_projection_test"
    operation = "details"


def test_full_details_survive_registry_without_enlarging_model_data():
    full_text = "FULL_REVIEW " + "readable " * 100
    normalized = format_place_details(
        {
            "id": "place",
            "delivery": False,
            "currentOpeningHours": {
                "nextOpenTime": "2026-10-03T12:00:00Z",
                "periods": [{"open": {"day": 6, "hour": 12}}],
            },
            "reviews": [
                {
                    "text": {"text": full_text},
                    "originalText": {"text": "DISPLAY_ORIGINAL"},
                    "rating": 4,
                }
            ],
        },
        language="en",
    )
    output = PlaceDetailsOutput().build_places_output([normalized])
    semantic = json.dumps(output.structured_data)
    assert full_text not in semantic
    assert "DISPLAY_ORIGINAL" not in semantic
    assert "periods" not in semantic
    assert "2026-10-03T12:00:00Z" in semantic
    assert "delivery" in semantic and "false" in semantic
    item = next(iter(output.registry_updates.values()))
    restored = RegistryItem.model_validate_json(item.model_dump_json())
    markup = PlaceCard().render(card_payload(restored), RenderContext())
    assert full_text in markup
    assert "DISPLAY_ORIGINAL" in markup


@pytest.mark.parametrize("invalid", [{"PRIVATE_TREE": True}, ["PRIVATE_TREE"], True])
def test_malformed_place_measurements_never_drop_card_or_display_raw_trees(invalid):
    html = PlaceCard().render(
        {
            "name": "KEPT_PLACE",
            "rating": 0,
            "userRatingCount": invalid,
            "price_level": invalid,
            "price_range": {"start": invalid, "currency": invalid},
            "distance": invalid,
            "primary_type": invalid,
        },
        RenderContext(),
    )
    assert "KEPT_PLACE" in html
    assert "PRIVATE_TREE" not in html
    assert "0/5" in html


@pytest.mark.parametrize("formatter", [_format_place, format_place_details])
@pytest.mark.parametrize("invalid", [None, True, {}, "2026-10-03T12:00:00", "2026-02-30T12:00:00Z"])
def test_invalid_clock_facts_never_enter_semantic_payload(formatter, invalid):
    result = formatter(
        {
            "id": "place",
            "timeZone": {"id": "Invalid/Timezone"},
            "currentOpeningHours": {"nextOpenTime": invalid, "openNow": "false"},
        },
        language="en",
    )
    assert "next_open_time" not in result
    assert "place_timezone" not in result
    assert "open_now" not in result


@pytest.mark.parametrize("instant", ["2026-10-03T12:00:00.123456789Z", "2026-10-03T12:00:00-03:30"])
def test_valid_rfc3339_precision_and_offset_survive_projection(instant):
    result = format_place_details(
        {"id": "place", "currentOpeningHours": {"nextOpenTime": instant}}, language="en"
    )
    assert result["next_open_time"] == instant
    assert PlaceCard()._get_next_open_time(result, RenderContext())


@pytest.mark.parametrize("formatter", [_format_place, format_place_details])
def test_structured_hours_and_timezone_survive_both_formatters(formatter: Callable):
    result = formatter(
        {
            "id": "place",
            "displayName": {"text": "Place"},
            "timeZone": {"id": "America/New_York"},
            "utcOffsetMinutes": -240,
            "currentOpeningHours": {
                "openNow": False,
                "nextOpenTime": "2026-10-05T13:30:00Z",
                "weekdayDescriptions": ["Dimanche: fermé", "Lundi: 09:30–18:00"],
            },
        },
        language="fr",
    )
    assert result["next_open_time"] == "2026-10-05T13:30:00Z"
    assert result["place_timezone"] == "America/New_York"
    assert (
        result[FIELD_DISPLAY_ONLY]["currentOpeningHours"]["nextOpenTime"]
        == result["next_open_time"]
    )
    html = PlaceCard().render(result, RenderContext(language="fr", timezone="Asia/Tokyo"))
    assert "09:30" in html
    assert "America/New_York" in html
    assert "Ouvre" in html


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_known_false_attributes_and_review_sources_remain_reachable(language):
    normalized = format_place_details(
        {
            "id": "place",
            "displayName": {"text": "Place"},
            "delivery": False,
            "takeout": True,
            "paymentOptions": {"acceptsDebitCards": True, "acceptsCashOnly": False},
            "accessibilityOptions": {"wheelchairAccessibleEntrance": False},
            "parkingOptions": {"valetParking": False},
            "reviews": [
                {
                    "text": {"text": "FULL_REVIEW"},
                    "rating": 4,
                    "publishTime": "2026-10-01T12:00:00Z",
                    "googleMapsUri": "https://example.test/review",
                    "authorAttribution": {
                        "displayName": "AUTHOR",
                        "uri": "https://example.test/author",
                        "photoUri": "https://example.test/avatar.jpg",
                    },
                }
            ],
        },
        language=language,
    )
    assert normalized["feature_states"] == {"takeout": True, "delivery": False}
    payload = {**normalized, **normalized[FIELD_DISPLAY_ONLY]}
    markup = PlaceCard().render(payload, RenderContext(language=language))
    assert "FULL_REVIEW" in markup
    assert 'href="https://example.test/author"' in markup
    assert 'href="https://example.test/review"' in markup
    assert 'src="https://example.test/avatar.jpg"' in markup
    assert 'data-availability="false"' in markup
    assert 'data-availability="true"' in markup


def test_localized_weekday_text_never_invents_a_next_transition():
    card = PlaceCard()
    ctx = RenderContext(language="fr")
    hours = {"opening_hours": ["Lundi: 09:00 – 18:00"] * 7}
    assert card._get_next_open_time(hours, ctx) == ""
    assert card._get_closing_time(hours, ctx) == ""


@pytest.mark.parametrize(
    "hours", [None, "bad", [], {"openNow": "false", "nextCloseTime": "tomorrow"}]
)
def test_malformed_optional_hours_preserve_the_place_without_a_false_status(hours):
    markup = PlaceCard().render(
        {"name": "KEPT_PLACE", "currentOpeningHours": hours}, RenderContext()
    )
    assert "KEPT_PLACE" in markup
    assert "lia-place--open" not in markup
    assert "lia-place--closed" not in markup


def test_overnight_structured_periods_remain_reachable_without_weekday_strings():
    markup = PlaceCard().render(
        {
            "name": "Place",
            "regularOpeningHours": {
                "periods": [
                    {
                        "open": {"day": 5, "hour": 18, "minute": 0},
                        "close": {"day": 6, "hour": 6, "minute": 0},
                    }
                ]
            },
        },
        RenderContext(language="en"),
    )
    assert "Friday" in markup and "Saturday" in markup
    assert "18:00" in markup and "06:00" in markup


@pytest.mark.parametrize("rating", [float("nan"), float("inf"), {"secret": "tree"}, True])
def test_bad_measurements_do_not_drop_other_place_data_or_dump_trees(rating):
    markup = PlaceCard().render(
        {"name": "KEPT_PLACE", "rating": rating, "types": [None, {"secret": "tree"}]},
        RenderContext(),
    )
    assert "KEPT_PLACE" in markup
    assert "secret" not in markup


@pytest.mark.parametrize("offset", [0, 330, 345, -210])
def test_supplied_fractional_offsets_use_the_central_aware_time_converter(offset):
    from src.domains.agents.display.components.place_hours import transition_time

    value = transition_time(
        {"next_open_time": "2026-10-05T13:30:00Z", "utc_offset_minutes": offset},
        RenderContext(language="fr"),
        opening=True,
    )
    total = 13 * 60 + 30 + offset
    assert f"{total // 60:02d}:{total % 60:02d}" in value
    assert "UTC" in value


@pytest.mark.parametrize("zone", ["../invalid", {"secret": "tree"}, None])
def test_unknown_place_zone_is_explicit_utc_instead_of_an_invented_local_time(zone):
    from src.domains.agents.display.components.place_hours import transition_time

    value = transition_time(
        {"next_open_time": "2026-10-05T13:30:00Z", "place_timezone": zone},
        RenderContext(language="fr", timezone="Asia/Tokyo"),
        opening=True,
    )
    assert "13:30" in value and value.endswith("UTC")
    assert "secret" not in value


def test_review_original_text_partial_visit_date_and_report_are_display_only():
    from src.domains.agents.display.components.place_reviews import render_place_reviews
    from src.domains.agents.tools.places_reviews import normalize_reviews

    source = {
        "text": {"text": "TRANSLATED"},
        "originalText": {"text": "ORIGINAL"},
        "rating": 4.5,
        "visitDate": {"year": 2026, "month": 9, "day": 0},
        "flagContentUri": "https://example.test/report",
        "authorAttribution": {"displayName": "AUTHOR"},
    }
    normalized = normalize_reviews([source])[0]
    assert normalized["original_text"] == "ORIGINAL"
    markup = "".join(render_place_reviews([normalized], RenderContext(language="fr")))
    assert "TRANSLATED" in markup and "ORIGINAL" in markup
    assert 'href="https://example.test/report"' in markup
    assert "septembre 2026" in markup and "4.5/5" in markup


def test_star_only_review_is_preserved_without_inventing_a_comment():
    from src.domains.agents.display.components.place_reviews import render_place_reviews

    markup = "".join(
        render_place_reviews([{"rating": 5, "author_name": "AUTHOR"}], RenderContext())
    )
    assert "AUTHOR" in markup and "5/5" in markup


def test_exception_dates_and_distinct_regular_hours_are_reachable():
    from src.domains.agents.display.components.place_hours import hours_content

    markup = hours_content(
        {
            "currentOpeningHours": {
                "weekdayDescriptions": ["SPECIAL_HOURS"],
                "specialDays": [{"date": {"year": 2026, "month": 12, "day": 25}}],
            },
            "regularOpeningHours": {"weekdayDescriptions": ["REGULAR_HOURS"]},
        },
        RenderContext(language="fr"),
    )
    assert "SPECIAL_HOURS" in markup and "REGULAR_HOURS" in markup
    assert "25 décembre 2026" in markup
