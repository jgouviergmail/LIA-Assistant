"""Temporal predicates are deterministic, with unresolved local times kept unknown."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from src.domains.agents.display.jev_collection_time import calendar_time_facts

pytestmark = pytest.mark.unit
REFERENCE = datetime(2026, 10, 4, 12, tzinfo=UTC)


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
