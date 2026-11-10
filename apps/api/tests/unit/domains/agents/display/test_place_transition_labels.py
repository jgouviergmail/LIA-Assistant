"""Place transition labels introduce a clock, followed by its full local date and zone."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n_v3 import V3Messages
from src.core.time_utils import convert_to_user_timezone
from src.domains.agents.display.components.base import RenderContext, escape_html, format_time
from src.domains.agents.display.components.place_card import PlaceCard
from src.domains.agents.display.components.place_hours import transition_time

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("opening", [True, False], ids=["opening", "closing"])
@pytest.mark.parametrize(
    ("language", "clock", "day"),
    [
        ("fr", "09:30", "lundi 5 octobre 2026"),
        ("en", "9:30 AM", "Monday, October 5, 2026"),
        ("de", "09:30", "Montag, 5. Oktober 2026"),
        ("es", "09:30", "lunes, 5 de octubre de 2026"),
        ("it", "09:30", "lunedì, 5 ottobre 2026"),
        ("zh-CN", "09:30", "2026年10月5日 星期一"),
    ],
)
def test_place_transition_uses_existing_clock_label_in_each_language(
    language: str, clock: str, day: str, opening: bool
) -> None:
    label = V3Messages.get_opens_at(language) if opening else V3Messages.get_closes_at(language)
    html = PlaceCard().render(
        {
            "name": "Place",
            "open_now": not opening,
            "place_timezone": "America/New_York",
            "next_open_time" if opening else "next_close_time": "2026-10-05T13:30:00Z",
        },
        RenderContext(language=language, timezone="Asia/Tokyo"),
    )
    assert escape_html(f"{label} {clock} · {day} · America/New_York") in html
    assert escape_html(f"{label} {day}") not in html


@pytest.mark.parametrize("opening", [True, False])
def test_fractional_place_offset_preserves_the_local_day_rollover(opening: bool) -> None:
    value = transition_time(
        {
            "utc_offset_minutes": 345,
            "next_open_time" if opening else "next_close_time": "2026-10-05T21:15:00Z",
        },
        RenderContext(language="en", timezone="America/New_York"),
        opening=opening,
    )
    assert value == "3:00 AM · Tuesday, October 6, 2026 · UTC+05:45"


@pytest.mark.parametrize(("offset", "expected"), [(0, "13:30"), (345, "19:15"), (-210, "10:00")])
def test_clock_accepts_explicit_provider_offsets(offset: int, expected: str) -> None:
    instant = datetime(2026, 10, 5, 13, 30, tzinfo=UTC)
    assert format_time(instant, "fr", timezone(timedelta(minutes=offset))) == expected


@pytest.mark.parametrize(
    ("instant", "expected"),
    [
        ("2026-03-08T06:30:00Z", "1:30 AM"),
        ("2026-03-08T07:30:00Z", "3:30 AM"),
        ("2026-11-01T05:30:00Z", "1:30 AM"),
        ("2026-11-01T06:30:00Z", "1:30 AM"),
    ],
)
def test_clock_preserves_dst_conversion(instant: str, expected: str) -> None:
    assert format_time(instant, "en", "America/New_York") == expected


def test_clock_keeps_the_declared_default_and_unknown_zone_fallback() -> None:
    instant = datetime(2026, 10, 5, 13, 30, tzinfo=timezone(timedelta(hours=3)))
    local = convert_to_user_timezone(instant, DEFAULT_USER_DISPLAY_TIMEZONE)
    assert local is not None
    assert format_time(instant, "fr") == local.strftime("%H:%M")
    assert format_time(instant, "fr", "Unknown/Zone") == "13:30"


@pytest.mark.parametrize("zone", ["", "../invalid"])
def test_clock_keeps_malformed_timezone_validation(zone: str) -> None:
    with pytest.raises(ValueError):
        format_time("2026-10-05T13:30:00Z", "fr", zone)


@pytest.mark.parametrize("value", [None, "", "not-a-date", "invalidTdate", "09:30"])
def test_clock_keeps_empty_and_unreadable_value_behavior(value: str | None) -> None:
    assert format_time(value, "fr", "UTC") == (value or "")


def test_clock_keeps_an_unzoned_value_as_a_wall_clock() -> None:
    assert format_time("2026-10-05T09:30:00", "en", "America/New_York") == "9:30 AM"
