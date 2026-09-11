"""Whether someone is in a meeting right now — the one question the cooldowns
never asked.

Nothing stopped the heartbeat interrupting a meeting. The nearest guard is the
activity cooldown, and it answers a different question: « did this person just
type? ». Someone in a meeting precisely does not type, so the existing guard
reads that silence as availability — it is the moment it believes them MOST
available.

The exclusions mirror the follow-up score, for the same reasons: a solo slot is
a block in a calendar, an all-day event is not an occupation, and an event they
declined is not one they are in.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from src.domains.moments.busy import is_in_meeting

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 11, 14, 30, tzinfo=UTC)
UTC_TZ = ZoneInfo("UTC")
ME = "moi@example.com"


def _event(
    *,
    starts_in: int = -30,
    duration: int = 60,
    guests: int = 2,
    **overrides: Any,
) -> dict[str, Any]:
    """A meeting in progress right now unless an override says otherwise."""
    start = NOW + timedelta(minutes=starts_in)
    attendees = [{"email": ME, "responseStatus": "accepted"}] + [
        {"email": f"g{i}@example.com"} for i in range(guests - 1)
    ]
    event: dict[str, Any] = {
        "id": "evt-1",
        "summary": "Point budget",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": (start + timedelta(minutes=duration)).isoformat()},
        "attendees": attendees,
    }
    event.update(overrides)
    return event


def _busy(*events: dict[str, Any]) -> bool:
    return is_in_meeting(list(events), now=NOW, user_tz=UTC_TZ, user_email=ME)


class TestWhenSomeoneIsBusy:
    def test_a_meeting_in_progress(self) -> None:
        assert _busy(_event()) is True

    def test_one_of_several(self) -> None:
        assert _busy(_event(starts_in=-300, duration=30), _event()) is True

    def test_a_meeting_starting_exactly_now(self) -> None:
        assert _busy(_event(starts_in=0)) is True


class TestWhenTheyAreNot:
    def test_no_events_at_all(self) -> None:
        assert _busy() is False

    def test_a_meeting_that_just_ended(self) -> None:
        """And this is precisely when a follow-up moment wants to speak."""
        assert _busy(_event(starts_in=-90, duration=60)) is False

    def test_a_meeting_about_to_start(self) -> None:
        assert _busy(_event(starts_in=15)) is False

    def test_a_solo_slot_is_not_a_meeting(self) -> None:
        """A focus block is time they set aside, not a room they are in."""
        assert _busy(_event(guests=1)) is False

    def test_an_event_with_no_attendee_list(self) -> None:
        event = _event()
        event.pop("attendees")

        assert _busy(event) is False

    def test_an_all_day_event_is_not_an_occupation(self) -> None:
        """« Conference week » does not mean « busy right now »."""
        event = _event()
        event["start"] = {"date": "2026-09-11"}
        event["end"] = {"date": "2026-09-12"}

        assert _busy(event) is False

    def test_a_declined_meeting_is_one_they_are_not_in(self) -> None:
        event = _event(
            attendees=[
                {"email": ME, "responseStatus": "declined"},
                {"email": "marc@example.com"},
            ]
        )

        assert _busy(event) is False

    def test_a_cancelled_meeting_is_not_happening(self) -> None:
        assert _busy(_event(status="cancelled")) is False


class TestItNeverRaises:
    def test_an_unreadable_event_is_simply_not_a_meeting(self) -> None:
        """Not knowing is not a reason to stay silent — nor to crash a tick."""
        assert _busy({"id": "x", "start": {"dateTime": "nope"}, "attendees": [{}, {}]}) is False

    def test_junk_in_the_list_is_stepped_over(self) -> None:
        assert (
            is_in_meeting(
                ["not an event", None, _event()],  # type: ignore[list-item]
                now=NOW,
                user_tz=UTC_TZ,
                user_email=ME,
            )
            is True
        )
