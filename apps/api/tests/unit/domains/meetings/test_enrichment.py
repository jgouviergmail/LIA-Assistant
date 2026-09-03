"""Calendar overlap and attendee hints (ADR-258) — pure selection logic."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.domains.meetings.enrichment import _attendee_names, _parse_when, best_overlap

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)


def _event(event_id: str, start: str, end: str) -> dict:
    return {"id": event_id, "start": {"dateTime": start}, "end": {"dateTime": end}}


def test_the_event_overlapping_the_recording_the_longest_wins() -> None:
    events = [
        _event("short", "2026-09-02T08:00:00+00:00", "2026-09-02T08:10:00+00:00"),
        _event("long", "2026-09-02T07:30:00+00:00", "2026-09-02T09:30:00+00:00"),
        _event("after", "2026-09-02T09:30:00+00:00", "2026-09-02T10:00:00+00:00"),
    ]
    chosen = best_overlap(events, T0, datetime(2026, 9, 2, 9, 0, tzinfo=UTC))
    assert chosen is not None and chosen["id"] == "long"


def test_no_overlap_and_malformed_events_yield_none() -> None:
    events = [
        _event("before", "2026-09-02T06:00:00+00:00", "2026-09-02T07:00:00+00:00"),
        {
            "id": "naive",
            "start": {"dateTime": "2026-09-02T08:00:00"},
            "end": {"dateTime": "2026-09-02T09:00:00"},
        },
        {"id": "broken", "start": {"dateTime": "not-a-date"}, "end": {}},
        {
            "id": "inverted",
            "start": {"dateTime": "2026-09-02T09:00:00+00:00"},
            "end": {"dateTime": "2026-09-02T08:00:00+00:00"},
        },
    ]
    assert best_overlap(events, T0, datetime(2026, 9, 2, 9, 0, tzinfo=UTC)) is None


def test_all_day_events_and_zulu_timestamps_are_parsed() -> None:
    assert _parse_when({"date": "2026-09-02"}) is None  # a bare date has no timezone → ignored
    parsed = _parse_when({"dateTime": "2026-09-02T08:00:00Z"})
    assert parsed == T0


def test_attendee_names_prefer_display_names_and_deduplicate() -> None:
    event = {
        "attendees": [
            {"displayName": "Marie", "email": "marie@example.org"},
            {"email": "paul@example.org"},
            {"displayName": "Marie"},
            "garbage",
            {},
        ]
    }
    assert _attendee_names(event) == ["Marie", "paul@example.org"]
