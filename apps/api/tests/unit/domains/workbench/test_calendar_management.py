"""Moving an event, managing calendars, in the « Tools » section (ADR-369, lot 5).

An event moves on the three providers; what a copy would reach is the client's refusal,
told in the page's words, and an event left in both calendars is said. A calendar of the
person's own is created, renamed and deleted; the account's main calendar and a calendar
someone else shares are neither renamed nor deleted, whatever a request names. A name a
calendar already answers to is refused: iCloud finds a calendar by its name.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.core.constants import WORKBENCH_CALENDAR_NAME_MAX_CHARS
from src.core.exceptions import BaseAPIException
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.calendar_management import (
    EventLeftBehindError,
    EventNotMovableError,
)
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import calendar_management, calendar_service, idempotency
from src.domains.workbench.errors import (
    EVENT_LEFT_BEHIND,
    ITEM_GONE,
    NAME_TAKEN,
    NOT_SUPPORTED_BY_PROVIDER,
)
from src.domains.workbench.features import PROVIDER_FEATURES, WorkbenchFeature
from src.domains.workbench.schemas.calendar import CalendarRename, EventMove, NewCalendar
from tests.unit.domains.workbench.fakes import FakeRedis

pytestmark = pytest.mark.unit

USER = uuid4()
PARIS = ZoneInfo("Europe/Paris")
KEY = "11111111-1111-4111-8111-111111111111"
GOOGLE, GRAPH, CALDAV = (
    ConnectorType.GOOGLE_CALENDAR,
    ConnectorType.MICROSOFT_CALENDAR,
    ConnectorType.APPLE_CALENDAR,
)
_MOVED = {
    "id": "copy",
    "summary": "Dentist",
    "start": {"dateTime": "2026-11-05T09:00:00+00:00"},
    "end": {"dateTime": "2026-11-05T10:00:00+00:00"},
}
#: A listing as Google gives it: the account's own, a calendar of its own, one shared.
_CALENDARS = {
    "items": [
        {"id": "main", "summary": "Me", "primary": True, "accessRole": "owner"},
        {"id": "mine", "summary": "Trips", "accessRole": "owner"},
        {"id": "shared", "summary": "Team", "accessRole": "writer"},
        {"id": "holidays", "summary": "Holidays", "accessRole": "reader"},
    ]
}


@pytest.fixture(autouse=True)
def _redis() -> Any:
    with patch.object(idempotency, "get_redis_cache", AsyncMock(return_value=FakeRedis())):
        yield


def _door(client: Any, kind: ConnectorType = GOOGLE) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any, container: Any = None) -> AsyncIterator[ActiveClient]:
        assert user_id == USER
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(calendar_management, "open_tool_client", opened)


def _client(**answers: Any) -> MagicMock:
    client = MagicMock(
        list_calendars=AsyncMock(return_value=_CALENDARS),
        move_event=AsyncMock(return_value=_MOVED),
        create_calendar=AsyncMock(return_value={"id": "new", "summary": "Sport"}),
        rename_calendar=AsyncMock(return_value={"id": "mine", "summary": "Sport"}),
        delete_calendar=AsyncMock(return_value=None),
    )
    client.configure_mock(**answers)
    return client


def _code(caught: pytest.ExceptionInfo[BaseAPIException]) -> Any:
    return caught.value.detail["code"]


class TestTheMove:
    REQUEST = EventMove(calendar_id="main", event_id="e1", destination_id="mine")

    @pytest.mark.parametrize("kind", [GOOGLE, GRAPH, CALDAV])
    async def test_it_reaches_the_client_and_answers_the_event_where_it_is_now(
        self, kind: ConnectorType
    ) -> None:
        client = _client()

        with _door(client, kind):
            detail = await calendar_management.move_event(USER, self.REQUEST)

        client.move_event.assert_awaited_once_with("e1", "main", "mine")
        assert (detail.id, detail.calendar_id) == ("copy", "mine")

    async def test_what_a_copy_would_reach_is_refused_in_the_page_s_words(self) -> None:
        client = _client(move_event=AsyncMock(side_effect=EventNotMovableError))

        with _door(client, GRAPH), pytest.raises(BaseAPIException) as caught:
            await calendar_management.move_event(USER, self.REQUEST)

        assert _code(caught) == NOT_SUPPORTED_BY_PROVIDER

    async def test_an_event_left_in_both_calendars_is_said(self) -> None:
        client = _client(move_event=AsyncMock(side_effect=EventLeftBehindError))

        with _door(client, GRAPH), pytest.raises(BaseAPIException) as caught:
            await calendar_management.move_event(USER, self.REQUEST)

        assert _code(caught) == EVENT_LEFT_BEHIND

    def test_an_event_goes_somewhere_else(self) -> None:
        with pytest.raises(ValidationError):
            EventMove(calendar_id="main", event_id="e1", destination_id="main")

    async def test_a_provider_without_the_gesture_is_refused_unsent(self) -> None:
        client = _client()
        features = {GOOGLE: frozenset()}

        with (
            _door(client),
            patch.object(calendar_management, "PROVIDER_FEATURES", features),
            pytest.raises(BaseAPIException) as caught,
        ):
            await calendar_management.move_event(USER, self.REQUEST)

        assert _code(caught) == NOT_SUPPORTED_BY_PROVIDER
        client.move_event.assert_not_awaited()

    def test_only_google_moves_an_event_with_its_guests(self) -> None:
        for kind in (GOOGLE, GRAPH, CALDAV):
            assert WorkbenchFeature.EVENT_MOVE in PROVIDER_FEATURES[kind]
        assert WorkbenchFeature.EVENT_MOVE_WITH_GUESTS in PROVIDER_FEATURES[GOOGLE]
        assert WorkbenchFeature.EVENT_MOVE_WITH_GUESTS not in PROVIDER_FEATURES[GRAPH]
        assert WorkbenchFeature.EVENT_MOVE_WITH_GUESTS not in PROVIDER_FEATURES[CALDAV]


class TestWhichCalendarsAreThePerson_s:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ({"id": "x", "accessRole": "owner"}, True),
            ({"id": "x", "accessRole": "writer"}, False),
            ({"id": "x", "accessRole": "reader"}, False),
            ({"id": "x", "accessRole": "owner", "primary": True}, False),
            # CalDAV publishes no role: its calendars are the account's own.
            ({"id": "x"}, True),
            ({"id": "x", "primary": True}, False),
            # Graph says it of each calendar, shared ones included.
            ({"id": "x", "accessRole": "writer", "removable": True}, True),
            ({"id": "x", "accessRole": "writer", "removable": False}, False),
        ],
    )
    def test_a_listing_says_which_may_be_managed(self, raw: dict[str, Any], expected: bool) -> None:
        assert calendar_service.calendar_info(raw, None).manageable is expected


class TestANewCalendar:
    REQUEST = NewCalendar(name="Sport", idempotency_key=KEY)

    @pytest.mark.parametrize("kind", [GOOGLE, GRAPH, CALDAV])
    async def test_it_is_created_in_the_account_s_zone(self, kind: ConnectorType) -> None:
        client = _client()

        with _door(client, kind):
            made = await calendar_management.create_calendar(USER, PARIS, self.REQUEST)

        client.create_calendar.assert_awaited_once_with("Sport", "Europe/Paris")
        assert (made.id, made.name) == ("new", "Sport")

    async def test_a_second_press_creates_nothing(self) -> None:
        client = _client()

        with _door(client):
            await calendar_management.create_calendar(USER, PARIS, self.REQUEST)
            with pytest.raises(BaseAPIException):
                await calendar_management.create_calendar(USER, PARIS, self.REQUEST)

        client.create_calendar.assert_awaited_once()

    @pytest.mark.parametrize("name", ["Trips", "trips", "HOLIDAYS"])
    async def test_a_name_a_calendar_answers_to_is_refused_unsent(self, name: str) -> None:
        client = _client()
        request = NewCalendar(name=name, idempotency_key=KEY)

        with _door(client), pytest.raises(BaseAPIException) as caught:
            await calendar_management.create_calendar(USER, PARIS, request)

        assert _code(caught) == NAME_TAKEN
        client.create_calendar.assert_not_awaited()

    def test_a_name_is_bounded(self) -> None:
        with pytest.raises(ValidationError):
            NewCalendar(name="  ", idempotency_key=KEY)
        with pytest.raises(ValidationError):
            NewCalendar(name="x" * (WORKBENCH_CALENDAR_NAME_MAX_CHARS + 1), idempotency_key=KEY)


class TestAChange:
    async def test_a_calendar_of_the_person_s_is_renamed(self) -> None:
        client = _client()

        with _door(client):
            renamed = await calendar_management.rename_calendar(
                USER, CalendarRename(calendar_id="mine", name="Sport")
            )

        client.rename_calendar.assert_awaited_once_with("mine", "Sport")
        assert renamed.name == "Sport"

    async def test_its_own_name_is_no_conflict(self) -> None:
        client = _client()

        with _door(client):
            await calendar_management.rename_calendar(
                USER, CalendarRename(calendar_id="mine", name="trips")
            )

        client.rename_calendar.assert_awaited_once()

    async def test_another_s_name_is_refused(self) -> None:
        client = _client()

        with _door(client), pytest.raises(BaseAPIException) as caught:
            await calendar_management.rename_calendar(
                USER, CalendarRename(calendar_id="mine", name="Team")
            )

        assert _code(caught) == NAME_TAKEN
        client.rename_calendar.assert_not_awaited()

    async def test_a_calendar_of_the_person_s_is_deleted(self) -> None:
        client = _client()

        with _door(client):
            await calendar_management.delete_calendar(USER, "mine")

        client.delete_calendar.assert_awaited_once_with("mine")

    @pytest.mark.parametrize("calendar_id", ["main", "shared", "holidays"])
    async def test_what_is_not_the_person_s_is_touched_by_no_request(
        self, calendar_id: str
    ) -> None:
        client = _client()

        with _door(client):
            with pytest.raises(BaseAPIException) as renaming:
                await calendar_management.rename_calendar(
                    USER, CalendarRename(calendar_id=calendar_id, name="Sport")
                )
            with pytest.raises(BaseAPIException) as deleting:
                await calendar_management.delete_calendar(USER, calendar_id)

        assert _code(renaming) == _code(deleting) == NOT_SUPPORTED_BY_PROVIDER
        client.rename_calendar.assert_not_awaited()
        client.delete_calendar.assert_not_awaited()

    async def test_a_provider_without_the_gesture_is_refused_unsent(self) -> None:
        client = _client()
        features = {GOOGLE: frozenset()}

        with (
            _door(client),
            patch.object(calendar_management, "PROVIDER_FEATURES", features),
            pytest.raises(BaseAPIException) as caught,
        ):
            await calendar_management.delete_calendar(USER, "mine")

        assert _code(caught) == NOT_SUPPORTED_BY_PROVIDER
        client.delete_calendar.assert_not_awaited()

    async def test_a_calendar_gone_is_said(self) -> None:
        client = _client()

        with _door(client), pytest.raises(BaseAPIException) as caught:
            await calendar_management.delete_calendar(USER, "gone")

        assert _code(caught) == ITEM_GONE
        client.delete_calendar.assert_not_awaited()
