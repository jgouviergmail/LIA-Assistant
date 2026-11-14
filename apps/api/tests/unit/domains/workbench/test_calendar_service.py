"""The calendar of the « Tools » section (ADR-369, Task 5.1).

A window is the account's days, each calendar drained up to the published
bound and answered on its own: cut, partly unreadable, or refused — the others
still answer, and only a window where every calendar fails is a refusal. A
create carries the provider's own idempotency; a change or a deletion reaches
the OCCURRENCE it names, and where the provider names an occurrence by its
series (CalDAV) a series is refused, never changed whole. Telling the
attendees is a choice only where the provider lets the page make it.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.constants import (
    WORKBENCH_CALENDAR_IDS_MAX,
    WORKBENCH_CALENDAR_WINDOW_MAX_DAYS,
    WORKBENCH_EVENT_REMINDER_MAX_MINUTES,
    WORKBENCH_EVENT_SEARCH_MAX,
    WORKBENCH_MAIL_QUERY_MAX_CHARS,
)
from src.core.exceptions import BaseAPIException, ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.calendar_answers import NotInvitedError
from src.domains.connectors.clients.calendar_options import EventOptions
from src.domains.connectors.clients.event_bounds import DayBounds
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.owner_defaults import CALENDAR
from src.domains.workbench import calendar_service
from src.domains.workbench.schemas.calendar import (
    EventChange,
    EventInvitationAnswer,
    EventSearchQuery,
    EventWindowQuery,
    NewEvent,
)

pytestmark = pytest.mark.unit

USER = uuid4()
PARIS = ZoneInfo("Europe/Paris")
GOOGLE, GRAPH, CALDAV = (
    ConnectorType.GOOGLE_CALENDAR,
    ConnectorType.MICROSOFT_CALENDAR,
    ConnectorType.APPLE_CALENDAR,
)
KEY = "11111111-1111-4111-8111-111111111111"


def _door(client: Any, kind: ConnectorType, preferred: str | None = None) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any, container: Any = None) -> AsyncIterator[ActiveClient]:
        # Only the calendar's own preference is ever read for a calendar.
        name = preferred if container is CALENDAR else None
        yield ActiveClient(client=client, connector_type=kind, preferred_name=name)

    return patch.object(calendar_service, "open_tool_client", opened)


def _timed(event_id: str = "e1", **overrides: Any) -> dict[str, Any]:
    return {
        "id": event_id,
        "summary": "Revue",
        "start": {"dateTime": "2026-11-02T10:00:00+01:00", "timeZone": "Europe/Paris"},
        "end": {"dateTime": "2026-11-02T11:00:00+01:00", "timeZone": "Europe/Paris"},
        **overrides,
    }


def _refused(status: int) -> ConnectorAPIError:
    return ConnectorAPIError(connector_type="google_calendar", status_code=status, detail="x")


class TestTheDefaultCalendar:
    @pytest.mark.parametrize(
        ("preferred", "expected"),
        [
            ("Team", "team@group.calendar.google.com"),
            (" team ", "team@group.calendar.google.com"),
            ("team@group.calendar.google.com", "team@group.calendar.google.com"),
            ("Somewhere else", None),
            (None, None),
        ],
    )
    async def test_it_is_named_as_the_settings_name_it(
        self, preferred: str | None, expected: str | None
    ) -> None:
        client = SimpleNamespace(
            list_calendars=AsyncMock(
                return_value={
                    "items": [
                        {"id": "primary", "summary": "Me", "primary": True},
                        {"id": "team@group.calendar.google.com", "summary": "Team"},
                    ]
                }
            )
        )

        with _door(client, ConnectorType.GOOGLE_CALENDAR, preferred):
            listed = await calendar_service.list_calendars(USER)

        assert [item.id for item in listed.calendars if item.default] == (
            [expected] if expected else []
        )


class TestTheCalendars:
    """The default the person chose in the settings is the one the page starts from."""

    ITEMS = [
        {"id": "own", "summary": "me@example.org", "primary": True, "accessRole": "owner"},
        {"id": "fam", "summary": "Famille", "accessRole": "owner"},
    ]

    async def test_the_chosen_default_is_named_whatever_its_case(self) -> None:
        client = MagicMock(list_calendars=AsyncMock(return_value={"items": self.ITEMS}))
        with _door(client, GOOGLE, preferred="  famille "):
            listed = await calendar_service.list_calendars(USER)

        assert [item.id for item in listed.calendars if item.default] == ["fam"]

    async def test_nothing_is_the_default_when_nothing_was_chosen(self) -> None:
        client = MagicMock(list_calendars=AsyncMock(return_value={"items": self.ITEMS}))
        with _door(client, GOOGLE):
            listed = await calendar_service.list_calendars(USER)

        assert not any(item.default for item in listed.calendars)

    async def test_a_chosen_name_no_calendar_holds_names_none(self) -> None:
        client = MagicMock(list_calendars=AsyncMock(return_value={"items": self.ITEMS}))
        with _door(client, GOOGLE, preferred="Travail"):
            listed = await calendar_service.list_calendars(USER)

        assert not any(item.default for item in listed.calendars)


class TestTheWindow:
    async def test_each_calendar_is_drained_up_to_the_bound_over_the_account_s_days(self) -> None:
        client = MagicMock(
            list_events_window=AsyncMock(return_value={"events": [_timed()], "truncated": True})
        )
        query = EventWindowQuery(
            calendar_ids=["primary"], start=date(2026, 11, 2), end=date(2026, 11, 8)
        )
        with _door(client, GOOGLE):
            window = await calendar_service.read_window(USER, PARIS, query)

        client.list_events_window.assert_awaited_once_with(
            "primary",
            "2026-11-01T23:00:00Z",
            "2026-11-08T23:00:00Z",
            bound=settings.workbench_calendar_window_max_events,
        )
        (only,) = window.calendars
        assert only.truncated is True
        assert (only.events[0].start, only.events[0].end) == (
            "2026-11-02T09:00:00Z",
            "2026-11-02T10:00:00Z",
        )

    async def test_a_cancelled_event_is_not_drawn_and_an_unreadable_one_is_counted(self) -> None:
        events = [
            _timed("ok"),
            _timed("gone", status="cancelled"),
            _timed("odd", start={"dateTime": "soon"}),
            # A start that is a day and an end that is an instant: no shape to draw.
            _timed("mixed", start={"date": "2026-11-02"}),
        ]
        client = MagicMock(
            list_events_window=AsyncMock(return_value={"events": events, "truncated": False})
        )
        with _door(client, GRAPH):
            window = await calendar_service.read_window(
                USER,
                PARIS,
                EventWindowQuery(
                    calendar_ids=["c1"], start=date(2026, 11, 2), end=date(2026, 11, 2)
                ),
            )

        (only,) = window.calendars
        assert [event.id for event in only.events] == ["ok"]
        assert only.skipped == 2

    async def test_a_calendar_that_fails_is_named_and_the_others_still_answer(self) -> None:
        async def drain(calendar_id: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            if calendar_id == "shared":
                raise _refused(403)
            return {"events": [_timed()], "truncated": False}

        client = MagicMock(list_events_window=AsyncMock(side_effect=drain))
        query = EventWindowQuery(
            calendar_ids=["primary", "shared"], start=date(2026, 11, 2), end=date(2026, 11, 2)
        )
        with _door(client, GOOGLE):
            window = await calendar_service.read_window(USER, PARIS, query)

        by_id = {entry.calendar_id: entry for entry in window.calendars}
        assert len(by_id["primary"].events) == 1 and by_id["primary"].error is None
        assert (by_id["shared"].events, by_id["shared"].error) == ([], "provider_refused")

    async def test_calendars_are_read_together_a_few_at_a_time(self) -> None:
        # A provider answers a burst with 429: up to 25 calendars never leave at once.
        running = 0
        peak = 0

        async def drain(calendar_id: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            running -= 1
            return {"events": [], "truncated": False}

        client = MagicMock(list_events_window=AsyncMock(side_effect=drain))
        query = EventWindowQuery(
            calendar_ids=[f"c{index}" for index in range(WORKBENCH_CALENDAR_IDS_MAX)],
            start=date(2026, 11, 2),
            end=date(2026, 11, 2),
        )
        with _door(client, GOOGLE):
            window = await calendar_service.read_window(USER, PARIS, query)

        assert len(window.calendars) == WORKBENCH_CALENDAR_IDS_MAX
        assert 1 < peak <= calendar_service.WINDOW_CONCURRENCY

    async def test_a_window_where_every_calendar_fails_is_the_refusal(self) -> None:
        client = MagicMock(list_events_window=AsyncMock(side_effect=_refused(401)))
        query = EventWindowQuery(
            calendar_ids=["a", "b"], start=date(2026, 11, 2), end=date(2026, 11, 2)
        )
        with _door(client, GOOGLE), pytest.raises(BaseAPIException) as caught:
            await calendar_service.read_window(USER, PARIS, query)

        assert caught.value.detail["code"] == "reconnect_required"

    def test_a_window_is_one_to_the_published_number_of_days(self) -> None:
        start = date(2026, 11, 1)
        EventWindowQuery(
            calendar_ids=["a"],
            start=start,
            end=date(2026, 11, WORKBENCH_CALENDAR_WINDOW_MAX_DAYS - 30),
        )
        with pytest.raises(ValidationError):
            EventWindowQuery(calendar_ids=["a"], start=start, end=date(2026, 12, 13))
        with pytest.raises(ValidationError):
            EventWindowQuery(calendar_ids=["a"], start=start, end=date(2026, 10, 31))


class TestTheDetail:
    async def test_a_description_graph_keeps_as_html_reads_as_text(self) -> None:
        raw = _timed(description="<html><body><p>Ordre du jour</p><p>Budget</p></body></html>")
        client = MagicMock(get_event=AsyncMock(return_value=raw))
        with _door(client, GRAPH):
            event = await calendar_service.read_event(USER, "c1", "e1")

        assert event.description is not None
        assert "<" not in event.description
        assert "Ordre du jour" in event.description and "Budget" in event.description

    @pytest.mark.parametrize(
        "uri", ["javascript:alert(1)", "data:text/html,x", "//evil.example/j", "meet.example/j"]
    )
    async def test_a_link_an_invitation_carries_is_kept_only_as_a_web_address(
        self, uri: str
    ) -> None:
        raw = _timed(
            hangoutLink=uri,
            conferenceData={"entryPoints": [{"entryPointType": "video", "uri": uri}]},
            htmlLink=uri,
        )
        client = MagicMock(get_event=AsyncMock(return_value=raw))
        with _door(client, GOOGLE):
            event = await calendar_service.read_event(USER, "c1", "e1")

        assert (event.conference_url, event.link) == (None, None)

    async def test_a_plain_description_is_left_as_written(self) -> None:
        raw = _timed(description="Ligne 1\n\nLigne 2 <pas une balise")
        client = MagicMock(get_event=AsyncMock(return_value=raw))
        with _door(client, GOOGLE):
            event = await calendar_service.read_event(USER, "c1", "e1")

        assert event.description == "Ligne 1\n\nLigne 2 <pas une balise"

    async def test_an_event_says_who_answered_what_and_where_its_call_is(self) -> None:
        raw = _timed(
            description="Ordre du jour",
            attendees=[
                {"email": "ana@example.org", "displayName": "Ana", "responseStatus": "accepted"},
                {"email": "bob@example.org", "responseStatus": "somethingNew"},
            ],
            organizer={"email": "me@example.org"},
            conferenceData={
                "entryPoints": [{"entryPointType": "video", "uri": "https://teams.example/j"}]
            },
            htmlLink="https://calendar.example/e1",
        )
        client = MagicMock(get_event=AsyncMock(return_value=raw))
        with _door(client, GRAPH):
            event = await calendar_service.read_event(USER, "c1", "e1")

        assert [(a.email, a.name, a.response) for a in event.attendees] == [
            ("ana@example.org", "Ana", "accepted"),
            ("bob@example.org", None, "needsAction"),
        ]
        assert (event.conference_url, event.organizer, event.link) == (
            "https://teams.example/j",
            "me@example.org",
            "https://calendar.example/e1",
        )


def _new(**overrides: Any) -> NewEvent:
    body: dict[str, Any] = {
        "calendar_id": "primary",
        "summary": "Revue",
        "start": "2026-11-02T10:00",
        "end": "2026-11-02T11:00",
        "timezone": "Europe/Paris",
        "idempotency_key": KEY,
        **overrides,
    }
    return NewEvent.model_validate(body)


class TestTheSearch:
    @staticmethod
    def _event(event_id: str, day: str) -> dict[str, Any]:
        return {
            "id": event_id,
            "summary": f"Event {event_id}",
            "start": {"date": day},
            "end": {"date": day},
        }

    async def test_every_calendar_is_asked_and_the_answer_reads_in_time_order(self) -> None:
        answers = {
            "work": {"items": [self._event("late", "2026-12-01")]},
            "home": {"items": [self._event("early", "2026-11-01")]},
        }

        async def list_events(**kwargs: Any) -> dict[str, Any]:
            return answers[kwargs["calendar_id"]]

        client = MagicMock(list_events=AsyncMock(side_effect=list_events))
        with _door(client, ConnectorType.GOOGLE_CALENDAR):
            found = await calendar_service.search_events(
                USER, PARIS, EventSearchQuery(q="budget", calendar_ids=["work", "home"])
            )

        assert [event.id for event in found.events] == ["early", "late"]
        assert found.events[0].calendar_id == "home"
        assert found.failed == []
        assert client.list_events.await_args.kwargs["query"] == "budget"

    async def test_it_searches_a_year_on_each_side_of_today(self) -> None:
        client = MagicMock(list_events=AsyncMock(return_value={"items": []}))
        with _door(client, ConnectorType.GOOGLE_CALENDAR):
            await calendar_service.search_events(
                USER, PARIS, EventSearchQuery(q="budget", calendar_ids=["work"])
            )

        asked = client.list_events.await_args.kwargs
        days = datetime.fromisoformat(asked["time_max"]) - datetime.fromisoformat(asked["time_min"])
        assert 2 * 365 - 2 <= days.days <= 2 * 366 + 2

    async def test_a_calendar_that_fails_is_named_and_the_others_still_answer(self) -> None:
        async def list_events(**kwargs: Any) -> dict[str, Any]:
            if kwargs["calendar_id"] == "work":
                raise ConnectorAPIError(connector_type="x", status_code=500, detail="x")
            return {"items": [self._event("e1", "2026-11-01")]}

        client = MagicMock(list_events=AsyncMock(side_effect=list_events))
        with _door(client, ConnectorType.GOOGLE_CALENDAR):
            found = await calendar_service.search_events(
                USER, PARIS, EventSearchQuery(q="budget", calendar_ids=["work", "home"])
            )

        assert [event.id for event in found.events] == ["e1"]
        assert found.failed == ["work"]

    async def test_a_search_where_every_calendar_fails_is_the_refusal(self) -> None:
        client = MagicMock(
            list_events=AsyncMock(
                side_effect=ConnectorAPIError(connector_type="x", status_code=500, detail="x")
            )
        )
        with _door(client, ConnectorType.GOOGLE_CALENDAR), pytest.raises(BaseAPIException):
            await calendar_service.search_events(
                USER, PARIS, EventSearchQuery(q="budget", calendar_ids=["work"])
            )

    async def test_the_answer_is_cut_at_its_bound_and_says_so(self) -> None:
        many = [
            self._event(f"e{n}", f"2026-11-{n + 1:02d}")
            for n in range(WORKBENCH_EVENT_SEARCH_MAX - 1)
        ]
        client = MagicMock(list_events=AsyncMock(return_value={"items": many}))
        with _door(client, ConnectorType.GOOGLE_CALENDAR):
            found = await calendar_service.search_events(
                USER, PARIS, EventSearchQuery(q="budget", calendar_ids=["work", "home"])
            )

        assert len(found.events) == WORKBENCH_EVENT_SEARCH_MAX
        assert found.truncated is True

    async def test_a_cancelled_event_is_no_answer(self) -> None:
        cancelled = {**self._event("e1", "2026-11-01"), "status": "cancelled"}
        client = MagicMock(list_events=AsyncMock(return_value={"items": [cancelled]}))
        with _door(client, ConnectorType.GOOGLE_CALENDAR):
            found = await calendar_service.search_events(
                USER, PARIS, EventSearchQuery(q="budget", calendar_ids=["work"])
            )

        assert found.events == []

    @pytest.mark.parametrize("words", ["", "   ", "x" * (WORKBENCH_MAIL_QUERY_MAX_CHARS + 1)])
    def test_words_are_read_before_anything_is_sent(self, words: str) -> None:
        with pytest.raises(ValidationError):
            EventSearchQuery(q=words, calendar_ids=["work"])


class TestTheOptions:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ({"reminderMinutes": 30}, 30),
            ({"reminders": {"overrides": [{"method": "popup", "minutes": 10}]}}, 10),
            ({"reminders": {"overrides": [{"minutes": 10}, {"minutes": 60}]}}, 60),
            ({"reminders": {"useDefault": True}}, None),
            ({}, None),
        ],
    )
    async def test_a_reminder_reads_the_same_on_every_provider(
        self, raw: dict[str, Any], expected: int | None
    ) -> None:
        event = {"id": "e1", "start": {"date": "2026-11-05"}, "end": {"date": "2026-11-06"}, **raw}
        client = MagicMock(get_event=AsyncMock(return_value=event))
        with _door(client, ConnectorType.GOOGLE_CALENDAR):
            detail = await calendar_service.read_event(USER, "primary", "e1")

        assert detail.reminder_minutes == expected

    @pytest.mark.parametrize(
        ("raw", "busy", "private"),
        [
            ({}, True, False),
            ({"transparency": "transparent"}, False, False),
            ({"visibility": "private"}, True, True),
        ],
    )
    async def test_busy_and_private_read_in_the_one_vocabulary(
        self, raw: dict[str, Any], busy: bool, private: bool
    ) -> None:
        event = {"id": "e1", "start": {"date": "2026-11-05"}, "end": {"date": "2026-11-06"}, **raw}
        client = MagicMock(get_event=AsyncMock(return_value=event))
        with _door(client, ConnectorType.GOOGLE_CALENDAR):
            detail = await calendar_service.read_event(USER, "primary", "e1")

        assert (detail.busy, detail.private) == (busy, private)

    async def test_a_change_carries_what_the_form_said(self) -> None:
        event = {"id": "e1", "start": {"date": "2026-11-05"}, "end": {"date": "2026-11-06"}}
        client = MagicMock(update_event=AsyncMock(return_value=event))
        with _door(client, ConnectorType.GOOGLE_CALENDAR):
            await calendar_service.update_event(
                USER,
                EventChange(
                    calendar_id="c1",
                    event_id="e1",
                    reminder_minutes=15,
                    busy=False,
                    conference=True,
                ),
            )

        kwargs = client.update_event.await_args.kwargs
        assert kwargs["options"] == EventOptions(reminder_minutes=15, busy=False)
        assert kwargs["add_conference"] is True

    async def test_a_call_is_refused_unsent_where_the_provider_has_none(self) -> None:
        client = MagicMock(update_event=AsyncMock())
        with (
            _door(client, ConnectorType.APPLE_CALENDAR),
            pytest.raises(BaseAPIException) as refused,
        ):
            await calendar_service.update_event(
                USER, EventChange(calendar_id="c1", event_id="e1", conference=True)
            )

        assert refused.value.detail["code"] == "not_supported_by_provider"
        client.update_event.assert_not_awaited()

    @pytest.mark.parametrize("minutes", [-2, WORKBENCH_EVENT_REMINDER_MAX_MINUTES + 1])
    def test_a_reminder_past_its_bounds_is_refused(self, minutes: int) -> None:
        with pytest.raises(ValidationError):
            EventChange(calendar_id="c1", event_id="e1", reminder_minutes=minutes)


class TestTheEventsOwnZone:
    """The zone an event was set in, read on every provider; never a zone nobody chose."""

    _AT = "2026-11-05T09:00:00+00:00"

    @pytest.mark.parametrize(
        ("zone", "own", "expected"),
        [
            # Google and CalDAV say it on the times.
            ("America/New_York", None, "America/New_York"),
            # Graph says it beside them, its times being in UTC.
            ("UTC", "Asia/Tokyo", "Asia/Tokyo"),
            # UTC is how a provider keeps an instant: nobody chose it.
            ("UTC", None, None),
            ("UTC", "Etc/UTC", None),
            ("GMT", None, None),
            # What no zone table holds is said by nobody.
            ("Custom/Somewhere", None, None),
            ("UTC", "tzone://Microsoft/Custom", None),
            (None, None, None),
        ],
    )
    async def test_it_is_read_on_every_provider(
        self, zone: str | None, own: str | None, expected: str | None
    ) -> None:
        start = {"dateTime": self._AT, **({"timeZone": zone} if zone else {})}
        event = {"id": "e1", "start": start, "end": start, **({"ownZone": own} if own else {})}
        client = MagicMock(get_event=AsyncMock(return_value=event))
        with _door(client, ConnectorType.GOOGLE_CALENDAR):
            detail = await calendar_service.read_event(USER, "primary", "e1")

        assert detail.zone == expected

    @pytest.mark.parametrize("own", [{}, {"ownZone": "Asia/Tokyo"}])
    async def test_a_day_has_no_zone(self, own: dict[str, str]) -> None:
        """Graph keeps ``originalStartTimeZone`` on an all-day event too."""
        event = {"id": "e1", "start": {"date": "2026-11-05"}, "end": {"date": "2026-11-06"}, **own}
        client = MagicMock(get_event=AsyncMock(return_value=event))
        with _door(client, ConnectorType.GOOGLE_CALENDAR):
            detail = await calendar_service.read_event(USER, "primary", "e1")

        assert detail.zone is None


class TestTheInvitation:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Google marks the person's own attendee.
            (
                {"attendees": [{"email": "a@x", "self": True, "responseStatus": "tentative"}]},
                "tentative",
            ),
            ({"attendees": [{"email": "a@x", "self": True}]}, "needsAction"),
            # Graph says it of the event.
            ({"myResponse": "declined"}, "declined"),
            # An event the person organises, or that does not name them, has nothing to answer.
            (
                {
                    "organizer": {"self": True},
                    "attendees": [{"email": "a@x", "self": True, "responseStatus": "accepted"}],
                },
                None,
            ),
            ({"attendees": [{"email": "a@x", "responseStatus": "accepted"}]}, None),
            ({}, None),
        ],
    )
    async def test_what_the_person_answered_is_read_on_every_provider(
        self, raw: dict[str, Any], expected: str | None
    ) -> None:
        event = {"id": "e1", "start": {"date": "2026-11-05"}, "end": {"date": "2026-11-06"}, **raw}
        client = MagicMock(get_event=AsyncMock(return_value=event))
        with _door(client, ConnectorType.GOOGLE_CALENDAR):
            detail = await calendar_service.read_event(USER, "primary", "e1")

        assert detail.my_response == expected

    async def test_an_answer_reaches_the_client_as_the_person_gave_it(self) -> None:
        client = MagicMock(respond_to_event=AsyncMock(return_value={}))
        with _door(client, ConnectorType.GOOGLE_CALENDAR):
            await calendar_service.answer_event(
                USER,
                EventInvitationAnswer(calendar_id="cal", event_id="e1", response="tentative"),
            )

        client.respond_to_event.assert_awaited_once_with("e1", "tentative", "cal")

    async def test_nothing_to_answer_is_refused(self) -> None:
        client = MagicMock(respond_to_event=AsyncMock(side_effect=NotInvitedError()))
        with (
            _door(client, ConnectorType.GOOGLE_CALENDAR),
            pytest.raises(BaseAPIException) as refused,
        ):
            await calendar_service.answer_event(
                USER,
                EventInvitationAnswer(calendar_id="cal", event_id="e1", response="accepted"),
            )

        assert refused.value.detail["code"] == "invalid_request"


class TestACreate:
    async def test_wall_times_and_their_zone_reach_the_client_with_the_provider_key(self) -> None:
        client = MagicMock(create_event=AsyncMock(return_value=_timed()))
        with _door(client, GOOGLE):
            await calendar_service.create_event(USER, _new(conference=True))

        kwargs = client.create_event.await_args.kwargs
        start, end = kwargs["bounds"].start, kwargs["bounds"].end
        assert (start.iso(), end.iso()) == ("2026-11-02T10:00:00", "2026-11-02T11:00:00")
        assert (start.zone.key, end.zone.key) == ("Europe/Paris", "Europe/Paris")
        # Ten on a Paris wall in November is nine in UTC: the zone travels with the time.
        assert start.instant() == datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
        assert (kwargs["idempotency_key"], kwargs["add_conference"]) == (KEY, True)

    async def test_an_all_day_event_reaches_the_client_as_days(self) -> None:
        raw = {
            "id": "e1",
            "summary": "Congé",
            "start": {"date": "2026-11-02"},
            "end": {"date": "2026-11-05"},
        }
        client = MagicMock(create_event=AsyncMock(return_value=raw))
        with _door(client, CALDAV):
            event = await calendar_service.create_event(
                USER, _new(all_day=True, start="2026-11-02", end="2026-11-05", timezone=None)
            )

        bounds = client.create_event.await_args.kwargs["bounds"]
        assert bounds == DayBounds(date(2026, 11, 2), date(2026, 11, 5), ZoneInfo("UTC"))
        assert (event.all_day, event.start, event.end) == (True, "2026-11-02", "2026-11-05")

    async def test_a_video_call_is_refused_unsent_where_the_provider_has_none(self) -> None:
        client = MagicMock(create_event=AsyncMock())
        with _door(client, CALDAV), pytest.raises(BaseAPIException) as caught:
            await calendar_service.create_event(USER, _new(conference=True))

        assert caught.value.detail["code"] == "not_supported_by_provider"
        client.create_event.assert_not_awaited()

    @pytest.mark.parametrize(
        "overrides",
        [
            {"start": "2026-11-02T10:00+01:00"},
            {"end": "2026-11-02T09:00"},
            {"timezone": None},
            {"timezone": "Mars/Olympus"},
            {"all_day": True, "start": "2026-11-02", "end": "2026-11-02"},
            {"attendees": ["not an address"]},
        ],
    )
    def test_what_cannot_be_a_wall_time_in_a_zone_is_refused(
        self, overrides: dict[str, Any]
    ) -> None:
        with pytest.raises(ValidationError):
            _new(**overrides)


def _change(**overrides: Any) -> EventChange:
    body: dict[str, Any] = {
        "calendar_id": "primary",
        "event_id": "e1_20261102T090000Z",
        **overrides,
    }
    return EventChange.model_validate(body)


class TestAChange:
    async def test_an_occurrence_is_changed_by_its_own_id(self) -> None:
        client = MagicMock(update_event=AsyncMock(return_value=_timed()), get_event=AsyncMock())
        with _door(client, GOOGLE):
            await calendar_service.update_event(USER, _change(summary="Revue"))

        assert client.update_event.await_args.args == ("e1_20261102T090000Z",)
        client.get_event.assert_not_awaited()

    async def test_a_series_is_refused_where_an_occurrence_is_named_by_it(self) -> None:
        client = MagicMock(
            get_event=AsyncMock(return_value=_timed(recurringEventId="uid-1")),
            update_event=AsyncMock(),
            delete_event=AsyncMock(),
        )
        with _door(client, CALDAV), pytest.raises(BaseAPIException) as caught:
            await calendar_service.update_event(USER, _change(summary="x"))
        assert caught.value.detail["code"] == "not_supported_by_provider"
        with _door(client, CALDAV), pytest.raises(BaseAPIException):
            await calendar_service.delete_event(
                USER, calendar_id="c", event_id="uid-1", notify=None
            )
        client.update_event.assert_not_awaited()
        client.delete_event.assert_not_awaited()

    async def test_a_single_caldav_event_is_changed(self) -> None:
        client = MagicMock(
            get_event=AsyncMock(return_value=_timed()),
            update_event=AsyncMock(return_value=_timed()),
        )
        with _door(client, CALDAV):
            await calendar_service.update_event(USER, _change(summary="x"))

        client.update_event.assert_awaited_once()

    @pytest.mark.parametrize(("notify", "told"), [(True, "all"), (False, "none"), (None, None)])
    async def test_google_tells_the_attendees_as_the_page_chose(
        self, notify: bool | None, told: str | None
    ) -> None:
        client = MagicMock(update_event=AsyncMock(return_value=_timed()))
        with _door(client, GOOGLE):
            await calendar_service.update_event(USER, _change(summary="x", notify=notify))

        assert client.update_event.await_args.kwargs["send_updates"] == told

    async def test_a_choice_is_refused_where_the_provider_tells_them_its_own_way(self) -> None:
        client = MagicMock(update_event=AsyncMock(), delete_event=AsyncMock())
        with _door(client, GRAPH), pytest.raises(BaseAPIException) as caught:
            await calendar_service.update_event(USER, _change(summary="x", notify=False))
        assert caught.value.detail["code"] == "not_supported_by_provider"
        with _door(client, GRAPH):
            await calendar_service.delete_event(USER, calendar_id="c", event_id="e", notify=None)
        client.update_event.assert_not_awaited()
        assert client.delete_event.await_args.kwargs["send_updates"] == "all"

    async def test_new_bounds_say_whether_they_are_days(self) -> None:
        with pytest.raises(ValidationError):
            _change(start="2026-11-02", end="2026-11-03")
        client = MagicMock(update_event=AsyncMock(return_value=_timed()))
        with _door(client, GOOGLE):
            await calendar_service.update_event(
                USER, _change(start="2026-11-02", end="2026-11-03", all_day=True)
            )
        bounds = client.update_event.await_args.kwargs["bounds"]
        assert bounds == DayBounds(date(2026, 11, 2), date(2026, 11, 3), ZoneInfo("UTC"))

    def test_a_change_naming_nothing_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            _change()
