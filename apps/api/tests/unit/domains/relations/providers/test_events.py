"""Meetings shared with one person — the right calendar, the right role.

Two things this fetcher must not get wrong:

- **which calendar.** Reading ``primary`` when the user's agenda lives in a
  named calendar is the defect ``connectors/preferences`` exists to close: it
  once answered that a peer was free at 10:00 while he had a meeting. The
  owner's configured default is resolved, always.
- **which role.** "Attends with me" and "organized it" are different facts.
  Apple's vCard-derived events carry no organizer at all, so the split is
  reported as UNKNOWN rather than as "organized nothing" — a negative nobody
  verified is not a result (ADR-184).

The provider search itself is not trusted: ``list_events(query=)`` has no
cross-provider parity and none of the three promises "this person is an
attendee". The window is fetched once and matched here, by address.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.relations.providers.client import CategoryClient
from src.domains.relations.providers.events import fetch_shared_events

pytestmark = pytest.mark.unit

USER_ID = uuid4()
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def _event(
    event_id: str,
    *,
    attendees: list[str] | None = None,
    organizer: str | None = None,
    hours: int = -2,
    duration_hours: int = 1,
    summary: str = "Point",
) -> dict:
    when = NOW + timedelta(hours=hours)
    event: dict = {
        "id": event_id,
        "summary": summary,
        "start": {"dateTime": when.isoformat()},
        "end": {"dateTime": (when + timedelta(hours=duration_hours)).isoformat()},
        "attendees": [{"email": address} for address in (attendees or [])],
    }
    if organizer is not None:
        event["organizer"] = {"email": organizer}
    return event


def _patched(events: list[dict], *, calendar_id: str = "agenda-perso"):
    import contextlib

    client = SimpleNamespace(list_events=AsyncMock(return_value={"items": events}))
    resolve = AsyncMock(return_value=calendar_id)

    @contextlib.asynccontextmanager
    async def _open(category, user_id):
        yield CategoryClient(client=client, connector_type="google_calendar", session=object())

    return (
        patch("src.domains.relations.providers.events.open_category_client", _open),
        patch("src.domains.relations.providers.events.resolve_owner_calendar_id", new=resolve),
        client,
        resolve,
    )


async def _fetch(events, addresses=("gerard@x.com",), limit=10, window_days=90, **kw):
    p_open, p_resolve, client, resolve = _patched(events, **kw)
    with p_open, p_resolve:
        found = await fetch_shared_events(
            USER_ID,
            addresses=list(addresses),
            limit=limit,
            window_days=window_days,
            now=NOW,
        )
    return found, client, resolve


class TestTheRightCalendar:
    async def test_reads_the_calendar_the_owner_configured(self) -> None:
        """Not ``primary``: that shortcut once reported a peer free while he
        had a 10:00 meeting in his named calendar."""
        _, client, resolve = await _fetch([])
        assert client.list_events.await_args.kwargs["calendar_id"] == "agenda-perso"
        assert resolve.await_args.kwargs["owner_id"] == USER_ID

    async def test_asks_the_provider_for_a_symmetric_window(self) -> None:
        _, client, _ = await _fetch([], window_days=30)
        kwargs = client.list_events.await_args.kwargs
        assert kwargs["time_min"].startswith("2026-06-30")
        assert kwargs["time_max"].startswith("2026-08-29")


class TestWhenItRunsFrom:
    """A meeting is a SLOT, not an instant — the card must be able to say so."""

    async def test_carries_both_ends_of_the_slot(self) -> None:
        found, _, _ = await _fetch(
            [_event("m", attendees=["gerard@x.com"], hours=24, duration_hours=2)]
        )
        assert found[0].starts_at == NOW + timedelta(hours=24)
        assert found[0].ends_at == NOW + timedelta(hours=26)

    async def test_an_all_day_event_carries_its_end_date(self) -> None:
        """Providers emit `date` for all-day events, end EXCLUSIVE."""
        found, _, _ = await _fetch(
            [
                {
                    "id": "allday",
                    "summary": "Congés",
                    "start": {"date": "2026-08-01"},
                    "end": {"date": "2026-08-03"},
                    "attendees": [{"email": "gerard@x.com"}],
                }
            ]
        )
        assert found[0].starts_at == datetime(2026, 8, 1, tzinfo=UTC)
        assert found[0].ends_at == datetime(2026, 8, 3, tzinfo=UTC)

    async def test_a_missing_end_is_null_rather_than_invented(self) -> None:
        """Some providers omit it. Guessing a duration would be a claim."""
        found, _, _ = await _fetch(
            [
                {
                    "id": "no-end",
                    "summary": "Point",
                    "start": {"dateTime": NOW.isoformat()},
                    "attendees": [{"email": "gerard@x.com"}],
                }
            ]
        )
        assert found[0].starts_at == NOW
        assert found[0].ends_at is None


class TestRoles:
    async def test_an_event_this_person_organized_is_marked_as_such(self) -> None:
        found, _, _ = await _fetch(
            [_event("theirs", attendees=["gerard@x.com"], organizer="gerard@x.com")]
        )
        assert [(event.id, event.role) for event in found] == [("theirs", "organizer")]

    async def test_an_event_they_merely_attend_is_marked_attendee(self) -> None:
        found, _, _ = await _fetch(
            [_event("mine", attendees=["gerard@x.com"], organizer="moi@x.com")]
        )
        assert [(event.id, event.role) for event in found] == [("mine", "attendee")]

    async def test_organizing_counts_even_without_an_attendee_line(self) -> None:
        """A meeting they organized and we joined may list us only."""
        found, _, _ = await _fetch(
            [_event("theirs", attendees=["moi@x.com"], organizer="gerard@x.com")]
        )
        assert [event.role for event in found] == ["organizer"]

    async def test_the_organizer_match_folds_case_but_not_accents(self) -> None:
        found, _, _ = await _fetch(
            [
                _event("cased", attendees=["moi@x.com"], organizer="Gerard@X.com"),
                _event("accented", attendees=["moi@x.com"], organizer="gérard@x.com"),
            ]
        )
        assert [event.id for event in found] == ["cased"]


class TestOrganizerKnown:
    async def test_a_provider_that_exposes_organizers_says_so(self) -> None:
        found, _, _ = await _fetch([_event("e", attendees=["gerard@x.com"], organizer="moi@x.com")])
        assert all(event.organizer_known for event in found)

    async def test_a_provider_that_exposes_none_reports_unknown(self) -> None:
        """Apple's events carry no organizer. Rendering "organized nothing"
        would be a negative nobody verified (ADR-184)."""
        found, _, _ = await _fetch([_event("e", attendees=["gerard@x.com"])])
        assert found and not any(event.organizer_known for event in found)
        assert [event.role for event in found] == ["attendee"]


class TestAttendeeMatching:
    async def test_keeps_only_the_events_this_person_is_part_of(self) -> None:
        found, _, _ = await _fetch(
            [
                _event("mine", attendees=["gerard@x.com"]),
                _event("someone-else", attendees=["autre@x.com"]),
            ]
        )
        assert [event.id for event in found] == ["mine"]

    async def test_any_of_the_persons_addresses_counts(self) -> None:
        found, _, _ = await _fetch(
            [_event("work", attendees=["g.dupont@acme.com"])],
            addresses=("home@x.com", "g.dupont@acme.com"),
        )
        assert [event.id for event in found] == ["work"]

    async def test_an_event_without_attendees_or_organizer_is_not_shared(self) -> None:
        found, _, _ = await _fetch([{"id": "solo", "summary": "Focus", "start": {}}])
        assert found == []


class TestOrderAndBoundaries:
    async def test_upcoming_first_then_the_most_recent_past(self) -> None:
        found, _, _ = await _fetch(
            [
                _event("past-old", attendees=["gerard@x.com"], hours=-48),
                _event("past-recent", attendees=["gerard@x.com"], hours=-2),
                _event("future", attendees=["gerard@x.com"], hours=24),
            ]
        )
        assert [event.id for event in found] == ["future", "past-recent", "past-old"]
        assert [event.is_past for event in found] == [False, True, True]

    async def test_the_cap_keeps_the_nearest(self) -> None:
        found, _, _ = await _fetch(
            [
                _event("far", attendees=["gerard@x.com"], hours=240),
                _event("near", attendees=["gerard@x.com"], hours=1),
            ],
            limit=1,
        )
        assert [event.id for event in found] == ["near"]

    async def test_an_all_day_event_still_places_itself(self) -> None:
        found, _, _ = await _fetch(
            [
                {
                    "id": "allday",
                    "summary": "Anniversaire",
                    "start": {"date": "2026-08-01"},
                    "attendees": [{"email": "gerard@x.com"}],
                }
            ]
        )
        assert [event.id for event in found] == ["allday"]
        assert found[0].is_past is False

    async def test_no_address_asks_nothing(self) -> None:
        p_open, p_resolve, client, _ = _patched([])
        with p_open, p_resolve:
            found = await fetch_shared_events(
                USER_ID, addresses=[], limit=10, window_days=90, now=NOW
            )
        assert found == []
        client.list_events.assert_not_awaited()

    async def test_a_provider_failure_propagates(self) -> None:
        """One call carries the WHOLE answer here, so swallowing it would
        report "no shared meetings" without having looked."""
        import contextlib

        client = SimpleNamespace(list_events=AsyncMock(side_effect=TimeoutError("slow")))

        @contextlib.asynccontextmanager
        async def _open(category, user_id):
            yield CategoryClient(client=client, connector_type="google_calendar", session=object())

        with (
            patch("src.domains.relations.providers.events.open_category_client", _open),
            patch(
                "src.domains.relations.providers.events.resolve_owner_calendar_id",
                new=AsyncMock(return_value="primary"),
            ),
            pytest.raises(TimeoutError),
        ):
            await fetch_shared_events(
                USER_ID, addresses=["a@x.com"], limit=10, window_days=90, now=NOW
            )

    async def test_a_summary_less_event_says_so_rather_than_rendering_blank(self) -> None:
        found, _, _ = await _fetch([_event("m", attendees=["gerard@x.com"], summary="  ")])
        assert found[0].summary == "(no title)"
