"""Meetings shared with one person — the right calendars, the right role.

Two things this fetcher must not get wrong:

- **which calendars.** Every calendar the account OWNS, the configured default
  first: the default says where an event is created, never where a meeting is.
  Reading it alone missed the invitation the main calendar held (measured
  2026-11-15), as reading ``primary`` alone once answered that a peer was free
  at 10:00 while his named calendar held a meeting. A calendar someone else
  shares is theirs, never read.
- **which role.** "Attends with me" and "organized it" are different facts.
  Apple's vCard-derived events carry no organizer at all, so the split is
  reported as UNKNOWN rather than as "organized nothing" — a negative nobody
  verified is not a result (ADR-184).

The provider search itself is not trusted: ``list_events(query=)`` has no
cross-provider parity and none of the three promises "this person is an
attendee". The window is read WHOLE and matched here, by address.

The fake calendar answers like the providers do: the window door drains its
pages, the agents' one-request listing answers the OLDEST events of a window
first and stops at the per-request ceiling. The card used to read through the
latter and never saw a meeting to come (measured 2026-11-15, ADR-185 amendment).
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.constants import CALENDARS_READ_MAX
from src.domains.connectors.calendar_access import CalendarAccess
from src.domains.connectors.clients.event_order import start_instant
from src.domains.relations.providers.events import (
    SharedEventsRead,
    event_instant,
    fetch_shared_events,
)

pytestmark = pytest.mark.unit

USER_ID = uuid4()
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
#: The agents' per-request ceiling the one-request listing stops at.
_CEILING = 25
#: The account's main calendar, under the id its provider lists it by.
_MAIN = "moi@x.com"


class _Calendar:
    """An account's calendars answering the three doors as the providers do.

    The configured default holds ``events``; ``held`` gives other calendars
    theirs; ``listing`` is what the provider lists (every held calendar, owned,
    when not given).
    """

    def __init__(
        self,
        events: list[dict[str, Any]],
        *,
        cut: bool = False,
        calendar_id: str = "agenda-perso",
        held: dict[str, list[dict[str, Any]]] | None = None,
        listing: list[dict[str, Any]] | None = None,
        listing_cut: bool = False,
    ) -> None:
        self.held = {calendar_id: events, **(held or {})}
        self.cut = cut
        self.listing = (
            [{"id": key, "accessRole": "owner"} for key in self.held]
            if listing is None
            else listing
        )
        self.listing_cut = listing_cut
        self.list_calendars = AsyncMock(side_effect=self._calendars)
        self.list_events_window = AsyncMock(side_effect=self._window)
        self.list_events = AsyncMock(side_effect=self._first_page)

    def read(self) -> list[str]:
        """The calendars a window was asked of, once per half, sorted."""
        return sorted(call.args[0] for call in self.list_events_window.await_args_list)

    async def _calendars(self, max_results: int = 100, show_hidden: bool = False) -> dict[str, Any]:
        page = self.listing[:max_results]
        return {"items": page, "truncated": self.listing_cut or len(self.listing) > len(page)}

    def _inside(self, calendar_id: str, time_min: str, time_max: str) -> list[dict[str, Any]]:
        """Google's reading of a window: the minimum bounds the END, the maximum the START."""
        low, high = datetime.fromisoformat(time_min), datetime.fromisoformat(time_max)

        def holds(event: dict[str, Any]) -> bool:
            start = event_instant(event, "start")
            if start is None:
                return True
            end = event_instant(event, "end") or start
            return end > low and start < high

        events = self.held.get(calendar_id, [])
        return sorted((event for event in events if holds(event)), key=start_instant)

    async def _window(
        self, calendar_id: str, time_min: str, time_max: str, *, bound: int
    ) -> dict[str, Any]:
        inside = self._inside(calendar_id, time_min, time_max)
        return {"events": inside[:bound], "truncated": self.cut or len(inside) > bound}

    async def _first_page(self, **kwargs: Any) -> dict[str, Any]:
        calendar_id = kwargs.get("calendar_id", "primary")
        inside = self._inside(calendar_id, kwargs["time_min"], kwargs["time_max"])
        page = inside[: min(kwargs.get("max_results", 10), _CEILING)]
        return {"items": page, "truncated": len(inside) > len(page)}


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


async def _shared_through(
    client: _Calendar,
    *,
    calendar_id: str = "agenda-perso",
    addresses: tuple[str, ...] = ("gerard@x.com",),
    limit: int = 10,
    window_days: int = 90,
) -> tuple[SharedEventsRead, list[object]]:
    """Ask for the meetings shared with gérard, the account's calendar door opening ``client``."""
    opened_for: list[object] = []

    @contextlib.asynccontextmanager
    async def _open(user_id):
        opened_for.append(user_id)
        yield CalendarAccess(
            client=client, calendar_id=calendar_id, connector_type="google_calendar"
        )

    with patch("src.domains.relations.providers.events.open_active_calendar", _open):
        found = await fetch_shared_events(
            USER_ID,
            addresses=list(addresses),
            limit=limit,
            window_days=window_days,
            now=NOW,
        )
    return found, opened_for


async def _read(
    events,
    addresses=("gerard@x.com",),
    limit=10,
    window_days=90,
    *,
    calendar_id: str = "agenda-perso",
    **calendars: Any,
):
    client = _Calendar(events, calendar_id=calendar_id, **calendars)
    found, opened_for = await _shared_through(
        client,
        calendar_id=calendar_id,
        addresses=tuple(addresses),
        limit=limit,
        window_days=window_days,
    )
    return found, client, opened_for


async def _fetch(events, addresses=("gerard@x.com",), limit=10, window_days=90, **kw):
    found, client, opened_for = await _read(events, addresses, limit, window_days, **kw)
    return found.events, client, opened_for


class TestTheRightCalendars:
    """The defect of 2026-11-15: the main calendar held the invitation, the default was named."""

    async def test_reads_the_calendar_the_owner_configured(self) -> None:
        """Not ``primary`` alone: that shortcut once reported a peer free while
        he had a 10:00 meeting in his named calendar."""
        _, client, opened_for = await _fetch([])
        # The OWNER's calendars: the door resolves them for the owner it is handed.
        assert set(client.read()) == {"agenda-perso"}
        assert opened_for == [USER_ID]

    async def test_a_meeting_in_the_main_calendar_is_found_while_the_default_is_named(
        self,
    ) -> None:
        hotpot = _event("hotpot", attendees=["gerard@x.com"], hours=6)
        found, client, _ = await _fetch(
            [],
            held={_MAIN: [hotpot]},
            listing=[
                {"id": _MAIN, "accessRole": "owner", "primary": True},
                {"id": "agenda-perso", "accessRole": "owner"},
            ],
        )
        assert [(event.id, event.is_past) for event in found] == [("hotpot", False)]
        assert set(client.read()) == {"agenda-perso", _MAIN}

    async def test_a_calendar_someone_else_shares_is_never_read(self) -> None:
        """A colleague's calendar, a holiday feed: their meetings are not the person's."""
        theirs = _event("theirs", attendees=["gerard@x.com"], hours=3)
        found, client, _ = await _fetch(
            [],
            held={"voisin@x.com": [theirs], "feries": [theirs]},
            listing=[
                {"id": "agenda-perso", "accessRole": "owner"},
                {"id": "voisin@x.com", "accessRole": "writer"},
                {"id": "feries", "accessRole": "reader"},
                {"id": "dispos", "accessRole": "freeBusyReader"},
            ],
        )
        assert found == []
        assert set(client.read()) == {"agenda-perso"}

    async def test_the_default_is_read_whatever_its_role(self) -> None:
        """Shared with the person or not, the default is where they create."""
        family = _event("famille", attendees=["gerard@x.com"], hours=3)
        found, client, _ = await _fetch(
            [family],
            calendar_id="agenda-famille",
            listing=[
                {"id": _MAIN, "accessRole": "owner", "primary": True},
                {"id": "agenda-famille", "accessRole": "writer"},
            ],
        )
        assert [event.id for event in found] == ["famille"]
        assert set(client.read()) == {"agenda-famille", _MAIN}

    async def test_the_main_calendar_is_read_once_under_its_own_id(self) -> None:
        """No default configured: ``primary`` names the main calendar the listing has."""
        _, client, _ = await _fetch(
            [],
            calendar_id="primary",
            held={_MAIN: []},
            listing=[{"id": _MAIN, "accessRole": "owner", "primary": True}],
        )
        assert client.read() == [_MAIN, _MAIN]

    async def test_a_meeting_two_calendars_hold_is_one_meeting(self) -> None:
        both = _event("both", attendees=["gerard@x.com"], hours=5)
        found, _, _ = await _fetch([both], held={_MAIN: [both]})
        assert [event.id for event in found] == ["both"]

    async def test_calendars_past_the_bound_are_said_as_a_cut(self) -> None:
        # The default listed LAST: a bound applied to the listing's order would drop it.
        listing = [{"id": f"agenda-{index}", "accessRole": "owner"} for index in range(30)]
        listing.append({"id": "agenda-perso", "accessRole": "owner"})
        found, client, _ = await _read([], listing=listing)
        assert len(set(client.read())) == CALENDARS_READ_MAX
        assert "agenda-perso" in client.read()
        assert found.cut is True

    async def test_a_listing_the_provider_cut_is_said(self) -> None:
        found, _, _ = await _read([], listing_cut=True)
        assert found.cut is True

    async def test_reads_the_coming_half_then_the_past_one(self) -> None:
        _, client, _ = await _fetch([], window_days=30)
        halves = [call.args[1:3] for call in client.list_events_window.await_args_list]
        assert [(low[:10], high[:10]) for low, high in halves] == [
            ("2026-07-30", "2026-08-29"),
            ("2026-06-30", "2026-07-30"),
        ]
        # The agents' one-request listing is never the card's door.
        client.list_events.assert_not_awaited()


class TestTheWholeWindow:
    """The defect of 2026-11-15: a busy past hid every meeting to come."""

    async def test_a_meeting_to_come_is_found_behind_a_busy_past(self) -> None:
        busy_past = [_event(f"past-{index}", hours=-24 * (index + 1)) for index in range(54)]
        busy_future = [_event(f"later-{index}", hours=48 + index) for index in range(33)]
        hotpot = _event("hotpot", attendees=["gerard@x.com"], hours=2)
        found, _, _ = await _fetch([*busy_past, hotpot, *busy_future])
        assert [event.id for event in found] == ["hotpot"]
        assert found[0].is_past is False

    async def test_a_cut_half_is_said(self) -> None:
        found, _, _ = await _read([_event("m", attendees=["gerard@x.com"])], cut=True)
        assert found.cut is True
        assert [event.id for event in found.events] == ["m"]

    async def test_a_whole_window_says_no_cut(self) -> None:
        found, _, _ = await _read([_event("m", attendees=["gerard@x.com"])])
        assert found.cut is False

    async def test_a_meeting_under_way_is_kept_once(self) -> None:
        """It ends after now and starts before: both halves hold it."""
        found, _, _ = await _fetch(
            [_event("now", attendees=["gerard@x.com"], hours=-1, duration_hours=2)]
        )
        assert [event.id for event in found] == ["now"]

    async def test_a_cancelled_meeting_is_not_shared(self) -> None:
        cancelled = {**_event("off", attendees=["gerard@x.com"], hours=3), "status": "cancelled"}
        found, _, _ = await _fetch([cancelled, _event("on", attendees=["gerard@x.com"], hours=4)])
        assert [event.id for event in found] == ["on"]


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
        found, client, _ = await _read([], addresses=())
        assert found.events == []
        assert found.cut is False
        client.list_calendars.assert_not_awaited()
        client.list_events_window.assert_not_awaited()

    async def test_a_provider_failure_propagates(self) -> None:
        """One read carries the WHOLE answer here, so swallowing it would
        report "no shared meetings" without having looked."""
        client = _Calendar([])
        client.list_events_window.side_effect = TimeoutError("slow")
        with pytest.raises(TimeoutError):
            await _shared_through(client)

    async def test_one_calendar_failing_fails_the_section(self) -> None:
        """Its own failure, not the group around it: « nothing shared » would be a guess."""
        client = _Calendar([], held={_MAIN: []})
        healthy = client.list_events_window.side_effect

        async def window(calendar_id: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            if calendar_id == _MAIN:
                raise ConnectionError("main calendar down")
            return await healthy(calendar_id, *args, **kwargs)

        client.list_events_window.side_effect = window
        with pytest.raises(ConnectionError):
            await _shared_through(client)

    async def test_a_listing_failure_propagates(self) -> None:
        """Reading the default alone would answer for calendars nobody read."""
        client = _Calendar([])
        client.list_calendars.side_effect = TimeoutError("slow")
        with pytest.raises(TimeoutError):
            await _shared_through(client)
        client.list_events_window.assert_not_awaited()

    async def test_a_summary_less_event_says_so_rather_than_rendering_blank(self) -> None:
        found, _, _ = await _fetch([_event("m", attendees=["gerard@x.com"], summary="  ")])
        assert found[0].summary == "(no title)"
