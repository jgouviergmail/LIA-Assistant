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
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.constants import WORKBENCH_CALENDAR_IDS_MAX, WORKBENCH_CALENDAR_WINDOW_MAX_DAYS
from src.core.exceptions import BaseAPIException, ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import calendar_service
from src.domains.workbench.schemas.calendar import EventChange, EventWindowQuery, NewEvent

pytestmark = pytest.mark.unit

USER = uuid4()
PARIS = ZoneInfo("Europe/Paris")
GOOGLE, GRAPH, CALDAV = (
    ConnectorType.GOOGLE_CALENDAR,
    ConnectorType.MICROSOFT_CALENDAR,
    ConnectorType.APPLE_CALENDAR,
)
KEY = "11111111-1111-4111-8111-111111111111"


def _door(client: Any, kind: ConnectorType) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

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


class TestACreate:
    async def test_wall_times_and_their_zone_reach_the_client_with_the_provider_key(self) -> None:
        client = MagicMock(create_event=AsyncMock(return_value=_timed()))
        with _door(client, GOOGLE):
            await calendar_service.create_event(USER, _new(conference=True))

        kwargs = client.create_event.await_args.kwargs
        assert (kwargs["start_datetime"], kwargs["end_datetime"], kwargs["timezone"]) == (
            "2026-11-02T10:00:00",
            "2026-11-02T11:00:00",
            "Europe/Paris",
        )
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

        kwargs = client.create_event.await_args.kwargs
        assert (kwargs["start_datetime"], kwargs["end_datetime"], kwargs["all_day"]) == (
            "2026-11-02",
            "2026-11-05",
            True,
        )
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
        kwargs = client.update_event.await_args.kwargs
        assert (kwargs["start_datetime"], kwargs["end_datetime"], kwargs["all_day"]) == (
            "2026-11-02",
            "2026-11-03",
            True,
        )

    def test_a_change_naming_nothing_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            _change()
