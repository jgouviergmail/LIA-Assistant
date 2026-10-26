"""Temporal predicates are deterministic, with unresolved local times kept unknown."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from src.domains.agents.display.jev_collection_time import calendar_time_facts, email_time_facts

pytestmark = pytest.mark.unit
REFERENCE = datetime(2026, 10, 4, 12, tzinfo=UTC)
# A Wednesday: 09:00 in Paris (CET since 10-25), 04:00 in New York (EDT until 11-01).
WEDNESDAY = datetime(2026, 10, 28, 8, tzinfo=UTC)


def _day(local_date: str, weekday: str, day_offset: int, week_offset: int) -> dict[str, object]:
    return {
        "local_date": local_date,
        "local_weekday": weekday,
        "day_offset": day_offset,
        "week_offset": week_offset,
    }


@pytest.mark.parametrize(
    "start,zone,expected",
    [
        (
            {"dateTime": "2026-10-29T10:00:00+01:00"},
            "Europe/Paris",
            _day("2026-10-29", "Thursday", 1, 0),
        ),
        ({"date": "2026-11-02"}, "Europe/Paris", _day("2026-11-02", "Monday", 5, 1)),
        # One instant, two people: their own clocks decide « today » and « tomorrow ».
        (
            {"dateTime": "2026-10-28T23:30:00Z"},
            "Europe/Paris",
            _day("2026-10-29", "Thursday", 1, 0),
        ),
        (
            {"dateTime": "2026-10-28T23:30:00Z"},
            "America/New_York",
            _day("2026-10-28", "Wednesday", 0, 0),
        ),
        # Monday 00:00 in Paris opens this week; one minute earlier is last week's Sunday.
        ({"dateTime": "2026-10-25T23:00:00Z"}, "Europe/Paris", _day("2026-10-26", "Monday", -2, 0)),
        (
            {"dateTime": "2026-10-25T22:59:00Z"},
            "Europe/Paris",
            _day("2026-10-25", "Sunday", -3, -1),
        ),
        (
            {"dateTime": "2026-10-30T15:00:00", "timeZone": "Asia/Shanghai"},
            "Asia/Shanghai",
            _day("2026-10-30", "Friday", 2, 0),
        ),
    ],
)
def test_an_event_start_states_its_day_in_the_persons_timezone(
    start: dict[str, str], zone: str, expected: dict[str, object]
) -> None:
    facts = calendar_time_facts({"start": start}, WEDNESDAY, zone)
    assert facts["start"] == {**expected, "all_day": "date" in start}
    assert facts["reference_local_weekday"] == "Wednesday"


@pytest.mark.parametrize("zone", [None, "invalid/zone"])
def test_an_event_day_needs_the_persons_known_timezone(zone: str | None) -> None:
    facts = calendar_time_facts({"start": {"dateTime": "2026-10-29T10:00:00Z"}}, WEDNESDAY, zone)
    assert "start" not in facts
    assert facts["reference_local_weekday"] is None


@pytest.mark.parametrize(
    "start",
    [{"dateTime": "2026-10-25T02:30:00", "timeZone": "Europe/Paris"}, {"dateTime": "tomorrow"}, {}],
)
def test_an_unresolved_event_start_states_no_day(start: dict[str, str]) -> None:
    assert "start" not in calendar_time_facts({"start": start}, WEDNESDAY, "Europe/Paris")


def _ms(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1000)


@pytest.mark.parametrize(
    "received,zone,expected",
    [
        (_ms("2026-10-28T07:30:00+00:00"), "Europe/Paris", _day("2026-10-28", "Wednesday", 0, 0)),
        # 00:30 on Wednesday in Paris is 19:30 on Tuesday in New York.
        (_ms("2026-10-27T23:30:00+00:00"), "Europe/Paris", _day("2026-10-28", "Wednesday", 0, 0)),
        (
            _ms("2026-10-27T23:30:00+00:00"),
            "America/New_York",
            _day("2026-10-27", "Tuesday", -1, 0),
        ),
        (
            str(_ms("2026-10-25T09:00:00+00:00")),
            "Europe/Paris",
            _day("2026-10-25", "Sunday", -3, -1),
        ),
    ],
)
def test_an_email_states_the_day_it_was_received_in_the_persons_timezone(
    received: int | str, zone: str, expected: dict[str, object]
) -> None:
    facts = email_time_facts({"internalDate": received}, WEDNESDAY, zone)
    assert facts["received"] == expected
    assert facts["reference_local_date"] == "2026-10-28"
    assert facts["reference_timezone"] == zone


@pytest.mark.parametrize("received", [None, "", "yesterday", "-5", 10**20, True, 1.5])
def test_an_unreadable_received_stamp_states_nothing(received: object) -> None:
    # A reference with no day of its own to compare would only enlarge the shared state.
    assert email_time_facts({"internalDate": received}, WEDNESDAY, "Europe/Paris") == {}


@pytest.mark.parametrize("zone", [None, "invalid/zone"])
def test_an_email_day_needs_the_persons_known_timezone(zone: str | None) -> None:
    received = {"internalDate": _ms("2026-10-28T07:30:00+00:00")}
    assert email_time_facts(received, WEDNESDAY, zone) == {}


def test_the_collection_question_names_only_facts_the_code_produces() -> None:
    import json
    import re
    from pathlib import Path

    question = json.loads(
        Path("src/domains/agents/prompts/v1/jev_collection_question.txt").read_text(
            encoding="utf-8"
        )
    )
    text = json.dumps(question["instructions"])
    named = set(re.findall(r"`([a-z_]+)`", text)) & {
        "start",
        "received",
        "day_offset",
        "week_offset",
        "local_weekday",
        "local_date",
    }
    produced = set(calendar_time_facts({"start": {"date": "2026-10-29"}}, WEDNESDAY, "UTC")) | set(
        email_time_facts({"internalDate": _ms("2026-10-28T07:30:00+00:00")}, WEDNESDAY, "UTC")
    )
    day_keys = set(_day("2026-10-29", "Thursday", 1, 0))
    assert {"start", "received", "day_offset", "week_offset", "local_weekday"} <= named
    assert named <= produced | day_keys


@pytest.mark.parametrize(
    "start,expected,granularity",
    [
        ({"dateTime": "2026-10-04T13:00:00Z"}, True, "instant"),
        ({"dateTime": "2026-10-04T12:00:00Z"}, True, "instant"),
        ({"dateTime": "2026-10-04T11:59:59Z"}, False, "instant"),
        ({"dateTime": "2026-10-04T13:00:00+02:00"}, False, "instant"),
        ({"dateTime": "2026-10-04T15:00:00+02:00"}, True, "instant"),
        ({"dateTime": "2026-10-04T15:00:00", "timeZone": "Europe/Paris"}, True, "instant"),
        ({"dateTime": "2026-10-04T13:00:00", "timeZone": "Europe/Paris"}, False, "instant"),
        ({"dateTime": "2026-10-04T15:00:00"}, None, None),
        ({"dateTime": "2026-10-04T15:00:00", "timeZone": "invalid/zone"}, None, None),
        ({"dateTime": "tomorrow"}, None, None),
        ({"dateTime": "2026-10-04"}, None, None),
        ({"dateTime": 123}, None, None),
        ({"date": "2026-10-05"}, True, "civil_date"),
        ({"date": "2026-10-04"}, True, "civil_date"),
        ({"date": "2026-10-03"}, False, "civil_date"),
        # The builder adds a synthetic midnight dateTime to all-day records.
        ({"date": "2026-10-04", "dateTime": "2026-10-04T00:00:00+02:00"}, True, "civil_date"),
        ({"date": "2026-02-30", "dateTime": "2026-10-05T12:00:00Z"}, None, None),
        ({}, None, None),
    ],
)
def test_source_time_is_compared_without_model_arithmetic(start, expected, granularity) -> None:
    payload = {"start": start, "summary": "Synthetic appointment"}
    original = deepcopy(payload)
    facts = calendar_time_facts(payload, REFERENCE, "Europe/Paris")
    assert facts["start_at_or_after_reference"] is expected
    assert facts["comparison_granularity"] == granularity
    assert facts["reference_datetime"] == "2026-10-04T12:00:00+00:00"
    assert facts["reference_local_date"] == "2026-10-04"
    assert payload == original


@pytest.mark.parametrize("timezone", [None, "invalid/zone"])
def test_all_day_needs_known_user_timezone(timezone: str | None) -> None:
    facts = calendar_time_facts({"start": {"date": "2026-10-04"}}, REFERENCE, timezone)
    assert facts["start_at_or_after_reference"] is None
    assert facts["reference_local_date"] is None


def test_all_day_comparison_uses_user_date_across_midnight() -> None:
    reference = datetime(2026, 10, 4, 23, tzinfo=UTC)
    facts = calendar_time_facts({"start": {"date": "2026-10-04"}}, reference, "Europe/Paris")
    assert facts["reference_local_date"] == "2026-10-05"
    assert facts["start_at_or_after_reference"] is False


@pytest.mark.parametrize("value", ["2026-10-25T02:30:00", "2026-03-29T02:30:00"])
def test_dst_fold_and_gap_without_offset_are_not_guessed(value: str) -> None:
    facts = calendar_time_facts(
        {"start": {"dateTime": value, "timeZone": "Europe/Paris"}}, REFERENCE, "Europe/Paris"
    )
    assert facts["start_at_or_after_reference"] is None


def test_explicit_offset_resolves_a_dst_fold() -> None:
    reference = datetime(2026, 10, 25, 0, 45, tzinfo=UTC)
    for offset, expected in [("+02:00", False), ("+01:00", True)]:
        facts = calendar_time_facts(
            {"start": {"dateTime": "2026-10-25T02:30:00" + offset}}, reference, "Europe/Paris"
        )
        assert facts["start_at_or_after_reference"] is expected


@pytest.mark.parametrize("start", [None, "2026-10-05T12:00:00Z", {}])
def test_unresolved_start_stays_unknown(start) -> None:
    assert (
        calendar_time_facts({"start": start}, REFERENCE, "UTC")["start_at_or_after_reference"]
        is None
    )


def test_naive_reference_is_not_interpreted_as_system_timezone() -> None:
    facts = calendar_time_facts(
        {"start": {"dateTime": "2026-10-05T12:00:00Z"}}, datetime(2026, 10, 4, 12), "UTC"
    )
    assert facts["start_at_or_after_reference"] is None
    assert facts["reference_datetime"] is None


@pytest.mark.parametrize(
    "start",
    [
        {"dateTime": "0001-01-01T00:00:00+01:00"},
        {"dateTime": "9999-12-31T23:59:59-01:00"},
        {"dateTime": "0001-01-01T00:00:00", "timeZone": "Europe/Paris"},
    ],
)
def test_source_utc_overflow_is_unresolved(start) -> None:
    facts = calendar_time_facts({"start": start}, REFERENCE, "Europe/Paris")
    assert facts["start_at_or_after_reference"] is None


def test_reference_utc_overflow_is_unresolved() -> None:
    reference = datetime.fromisoformat("0001-01-01T00:00:00+01:00")
    facts = calendar_time_facts({"start": {"date": "2026-10-04"}}, reference, "UTC")
    assert facts["reference_datetime"] is None
    assert facts["start_at_or_after_reference"] is None


def test_local_date_overflow_does_not_invent_a_civil_date() -> None:
    reference = datetime(1, 1, 1, tzinfo=UTC)
    facts = calendar_time_facts({"start": {"date": "2026-10-04"}}, reference, "America/New_York")
    assert facts["reference_datetime"] == "0001-01-01T00:00:00+00:00"
    assert facts["reference_local_date"] is None
    assert facts["start_at_or_after_reference"] is None
