"""Date-first agenda ranges preserve machine boundaries and legacy labels."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from src.domains.briefing.formatters import format_agenda_event

PARIS = ZoneInfo("Europe/Paris")
NOW = datetime(2026, 10, 15, 12, tzinfo=PARIS)


@pytest.fixture(autouse=True)
def fixed_reference() -> Iterator[None]:
    with patch("src.domains.briefing.formatters.datetime", wraps=datetime) as clock:
        clock.now.return_value = NOW
        yield


@pytest.mark.unit
@pytest.mark.parametrize(
    ("language", "word"),
    [
        ("fr", "demain"),
        ("en", "tomorrow"),
        ("de", "morgen"),
        ("es", "mañana"),
        ("it", "domani"),
        ("zh", "明天"),
    ],
)
def test_same_day_range_names_tomorrow_once(language: str, word: str) -> None:
    start = (NOW + timedelta(days=1)).replace(hour=10, minute=0, second=0)
    item = format_agenda_event(
        {
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": start.replace(hour=11).isoformat()},
        },
        PARIS,
        language,
    )
    assert item.time_range_local == f"{word} 10:00 – 11:00"
    assert item.start_local == f"10:00 {word}"
    assert item.end_local == f"11:00 {word}"


@pytest.mark.unit
@pytest.mark.parametrize("end", [None, {}, {"dateTime": "unreadable"}, "invalid"])
def test_unknown_end_preserves_existing_fallback(end: object) -> None:
    raw = {"start": {"dateTime": NOW.replace(hour=10, minute=0).isoformat()}, "end": end}
    item = format_agenda_event(raw, PARIS, "fr")
    assert item.time_range_local is None


@pytest.mark.unit
def test_all_day_preserves_the_existing_labels() -> None:
    item = format_agenda_event(
        {"start": {"date": "2026-10-15"}, "end": {"date": "2026-10-16"}}, PARIS, "fr"
    )
    assert item.time_range_local is None


@pytest.mark.unit
def test_midnight_keeps_both_civil_dates() -> None:
    item = format_agenda_event(
        {
            "start": {"dateTime": "2026-10-18T23:00:00+02:00"},
            "end": {"dateTime": "2026-10-19T01:00:00+02:00"},
        },
        PARIS,
        "fr",
    )
    assert item.time_range_local == "18/10/2026 23:00 – 19/10/2026 01:00"


@pytest.mark.unit
def test_repeated_dst_hour_keeps_both_offsets() -> None:
    item = format_agenda_event(
        {
            "start": {"dateTime": "2026-10-25T02:45:00+02:00"},
            "end": {"dateTime": "2026-10-25T02:15:00+01:00"},
        },
        PARIS,
        "fr",
    )
    assert item.time_range_local == "25/10/2026 02:45 (UTC+02:00) – 02:15 (UTC+01:00)"


@pytest.mark.unit
def test_inverted_end_falls_back_without_inventing_a_duration() -> None:
    item = format_agenda_event(
        {
            "start": {"dateTime": "2026-10-18T11:00:00+02:00"},
            "end": {"dateTime": "2026-10-18T10:00:00+02:00"},
        },
        PARIS,
        "fr",
    )
    assert item.time_range_local is None


@pytest.mark.unit
@pytest.mark.parametrize("start", [None, {}, "invalid", {"dateTime": "unreadable"}])
def test_unreadable_start_never_invents_a_range(start: object) -> None:
    item = format_agenda_event(
        {"start": start, "end": {"dateTime": "2026-10-16T11:00:00+02:00"}}, PARIS, "fr"
    )
    assert item.time_range_local is None


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["google", "microsoft", "apple"])
def test_provider_local_time_conventions_are_preserved(provider: str) -> None:
    if provider == "google":
        start, end = {"dateTime": "2026-10-16T08:00:00Z"}, {"dateTime": "2026-10-16T09:00:00Z"}
    elif provider == "microsoft":
        start = {"dateTime": "2026-10-16T08:00:00", "timeZone": "UTC"}
        end = {"dateTime": "2026-10-16T09:00:00", "timeZone": "UTC"}
    else:
        start, end = {"dateTime": "2026-10-16T10:00:00"}, {"dateTime": "2026-10-16T11:00:00"}
    assert (
        format_agenda_event({"start": start, "end": end}, PARIS, "fr").time_range_local
        == "demain 10:00 – 11:00"
    )
