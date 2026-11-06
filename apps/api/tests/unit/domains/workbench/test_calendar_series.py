"""A repeating event, and a whole series (ADR-369, lot 10).

A series starts on the event's own day: the rule is anchored there, and a rule that day does not
belong to is refused before anything is sent, because each provider would answer it differently.
Changing a whole series keeps its first day and takes the new time of day and the new length: an
occurrence's date is no date for the series. An occurrence of a series is its own act, as it was.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.constants import WORKBENCH_EVENT_SERIES_MAX_COUNT
from src.core.exceptions import BaseAPIException
from src.core.recurrence import DailyTimes, RecurrenceSpec, SeriesEnd, TimeOfDay
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.event_recurrence import RecurrenceNotHeldError
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import calendar_series, calendar_service
from src.domains.workbench.errors import (
    EVENT_START_OUTSIDE_SERIES,
    INVALID_REQUEST,
    NOT_SUPPORTED_BY_PROVIDER,
    refusal_code_of,
)
from src.domains.workbench.schemas.calendar import EventChange, NewEvent

pytestmark = pytest.mark.unit

USER = uuid4()
KEY = "11111111-1111-4111-8111-111111111111"
GOOGLE, GRAPH, CARDDAV = (
    ConnectorType.GOOGLE_CALENDAR,
    ConnectorType.MICROSOFT_CALENDAR,
    ConnectorType.APPLE_CALENDAR,
)
ZONE = "Europe/Paris"
MONDAY = date(2027, 1, 4)


def _door(client: Any, kind: ConnectorType = GOOGLE) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any, container: Any = None) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(calendar_service, "open_tool_client", opened)


def _spec(freq: str = "weekly", **fields: Any) -> RecurrenceSpec:
    if freq == "weekly" and "byweekday" not in fields:
        fields["byweekday"] = (1,)
    return RecurrenceSpec(
        freq=freq,
        times=DailyTimes(mode="at", at=[TimeOfDay(hour=12, minute=0)]),
        anchor_date=date(2020, 1, 1),
        **fields,
    )


def _raw(**fields: Any) -> dict[str, Any]:
    return {
        "id": "e1",
        "summary": "Standup",
        "start": {"dateTime": "2027-01-04T09:00:00+01:00"},
        "end": {"dateTime": "2027-01-04T09:30:00+01:00"},
        **fields,
    }


def _new(**fields: Any) -> NewEvent:
    return NewEvent.model_validate(
        {
            "calendar_id": "primary",
            "summary": "Standup",
            "start": "2027-01-04T09:00",
            "end": "2027-01-04T09:30",
            "timezone": ZONE,
            "idempotency_key": KEY,
            **fields,
        }
    )


def _change(**fields: Any) -> EventChange:
    return EventChange.model_validate(
        {"calendar_id": "primary", "event_id": "e1_20270111", "scope": "series", **fields}
    )


class TestASeriesAnchored:
    def test_it_starts_on_the_event_s_own_day(self) -> None:
        anchored = calendar_series.spec_from(_spec(), MONDAY, ZONE)

        assert anchored.anchor_date == MONDAY

    def test_a_day_the_rule_does_not_serve_is_refused(self) -> None:
        with pytest.raises(BaseAPIException) as refused:
            calendar_series.spec_from(_spec(byweekday=(3,)), MONDAY, ZONE)

        assert refusal_code_of(refused.value) == EVENT_START_OUTSIDE_SERIES

    def test_what_the_rule_reads_of_a_time_is_never_the_event_s(self) -> None:
        anchored = calendar_series.spec_from(_spec("daily"), MONDAY, ZONE)

        assert anchored.anchor_date == MONDAY

    def test_a_count_past_the_bound_is_refused(self) -> None:
        end = SeriesEnd(kind="after_count", after_count=WORKBENCH_EVENT_SERIES_MAX_COUNT + 1)

        with pytest.raises(BaseAPIException) as refused:
            calendar_series.spec_from(_spec("daily", end=end), MONDAY, ZONE)

        assert refusal_code_of(refused.value) == INVALID_REQUEST

    def test_once_is_no_series(self) -> None:
        with pytest.raises(BaseAPIException) as refused:
            calendar_series.spec_from(_spec("once"), MONDAY, ZONE)

        assert refusal_code_of(refused.value) == INVALID_REQUEST


class TestCreating:
    async def test_a_series_rides_the_options_from_its_own_first_day(self) -> None:
        client = MagicMock(create_event=AsyncMock(return_value=_raw()))

        with _door(client):
            await calendar_service.create_event(
                USER, _new(recurrence=_spec().model_dump(mode="json"))
            )

        options = client.create_event.await_args.kwargs["options"]
        assert options.recurrence.anchor_date == MONDAY
        assert options.zone == ZONE
        assert options.all_day is False

    async def test_an_all_day_series_says_so(self) -> None:
        client = MagicMock(create_event=AsyncMock(return_value=_raw()))
        request = _new(
            start="2027-01-04",
            end="2027-01-05",
            all_day=True,
            recurrence=_spec().model_dump(mode="json"),
        )

        with _door(client):
            await calendar_service.create_event(USER, request)

        options = client.create_event.await_args.kwargs["options"]
        assert options.all_day is True
        assert options.recurrence.anchor_date == MONDAY

    async def test_an_event_with_none_carries_none(self) -> None:
        client = MagicMock(create_event=AsyncMock(return_value=_raw()))

        with _door(client):
            await calendar_service.create_event(USER, _new())

        assert client.create_event.await_args.kwargs["options"].recurrence is None

    async def test_a_shape_the_provider_cannot_hold_is_said_by_name(self) -> None:
        client = MagicMock(create_event=AsyncMock(side_effect=RecurrenceNotHeldError("no")))

        with _door(client, GRAPH), pytest.raises(BaseAPIException) as refused:
            await calendar_service.create_event(
                USER, _new(recurrence=_spec().model_dump(mode="json"))
            )

        assert refusal_code_of(refused.value) == NOT_SUPPORTED_BY_PROVIDER


class TestChangingAWholeSeries:
    def _client(self, occurrence: dict[str, Any], master: dict[str, Any]) -> MagicMock:
        answers = {"e1_20270111": occurrence, "e1": master}
        return MagicMock(
            get_event=AsyncMock(side_effect=lambda event_id, calendar_id: answers[event_id]),
            update_event=AsyncMock(return_value=master),
            delete_event=AsyncMock(return_value={}),
        )

    occurrence = _raw(id="e1_20270111", recurringEventId="e1")
    master = _raw(recurrence=["RRULE:FREQ=WEEKLY;BYDAY=MO"])

    async def test_it_reaches_the_master_not_the_occurrence(self) -> None:
        client = self._client(self.occurrence, self.master)

        with _door(client):
            await calendar_service.update_event(USER, _change(summary="Retro"))

        assert client.update_event.await_args.args[0] == "e1"
        assert client.update_event.await_args.kwargs["summary"] == "Retro"

    async def test_a_new_time_keeps_the_series_first_day(self) -> None:
        client = self._client(self.occurrence, self.master)
        request = _change(
            start="2027-01-11T10:15",
            end="2027-01-11T11:00",
            all_day=False,
            timezone=ZONE,
        )

        with _door(client):
            await calendar_service.update_event(USER, request)

        kwargs = client.update_event.await_args.kwargs
        assert kwargs["start_datetime"] == "2027-01-04T10:15:00"
        assert kwargs["end_datetime"] == "2027-01-04T11:00:00"

    async def test_a_time_past_midnight_stays_as_long(self) -> None:
        client = self._client(self.occurrence, self.master)
        request = _change(
            start="2027-01-11T23:30",
            end="2027-01-12T00:30",
            all_day=False,
            timezone=ZONE,
        )

        with _door(client):
            await calendar_service.update_event(USER, request)

        assert client.update_event.await_args.kwargs["end_datetime"] == "2027-01-05T00:30:00"

    async def test_an_all_day_series_keeps_its_first_day_and_its_length(self) -> None:
        master = _raw(start={"date": "2027-01-04"}, end={"date": "2027-01-05"}, recurrence=["x"])
        occurrence = {**master, "id": "e1_20270111", "recurringEventId": "e1"}
        client = self._client(occurrence, master)
        request = _change(start="2027-01-11", end="2027-01-13", all_day=True)

        with _door(client):
            await calendar_service.update_event(USER, request)

        kwargs = client.update_event.await_args.kwargs
        assert kwargs["start_datetime"] == "2027-01-04"
        assert kwargs["end_datetime"] == "2027-01-06"

    async def test_a_new_rule_starts_on_the_series_first_day(self) -> None:
        client = self._client(self.occurrence, self.master)
        request = _change(recurrence=_spec().model_dump(mode="json"), timezone=ZONE)

        with _door(client):
            await calendar_service.update_event(USER, request)

        options = client.update_event.await_args.kwargs["options"]
        assert options.recurrence.anchor_date == MONDAY

    async def test_a_rule_alone_on_an_all_day_series_ends_on_a_day(self) -> None:
        master = _raw(start={"date": "2027-01-04"}, end={"date": "2027-01-05"}, recurrence=["x"])
        occurrence = {**master, "id": "e1_20270111", "recurringEventId": "e1"}
        client = self._client(occurrence, master)

        with _door(client):
            await calendar_service.update_event(
                USER, _change(recurrence=_spec().model_dump(mode="json"), timezone=ZONE)
            )

        assert client.update_event.await_args.kwargs["options"].all_day is True

    async def test_a_title_alone_reads_no_first_day(self) -> None:
        master = _raw(start={}, recurrence=["x"])
        occurrence = {**master, "id": "e1_20270111", "recurringEventId": "e1"}
        client = self._client(occurrence, master)
        client.update_event = AsyncMock(return_value=_raw())

        with _door(client):
            await calendar_service.update_event(USER, _change(summary="Retro"))

        client.update_event.assert_awaited_once()

    async def test_a_graph_master_is_a_series_though_its_recurrence_is_apart(self) -> None:
        master = _raw(recurrence=[], recurrence_pattern={"pattern": {"type": "weekly"}})
        client = MagicMock(
            get_event=AsyncMock(return_value=master),
            update_event=AsyncMock(return_value=master),
        )

        with _door(client, GRAPH):
            await calendar_service.update_event(
                USER,
                EventChange.model_validate(
                    {"calendar_id": "primary", "event_id": "e1", "scope": "series", "summary": "x"}
                ),
            )

        assert client.update_event.await_args.args[0] == "e1"

    async def test_an_event_that_is_no_series_is_refused_unsent(self) -> None:
        client = self._client(_raw(id="e1_20270111"), self.master)

        with _door(client), pytest.raises(BaseAPIException) as refused:
            await calendar_service.update_event(USER, _change(summary="Retro"))

        assert refusal_code_of(refused.value) == INVALID_REQUEST
        client.update_event.assert_not_awaited()

    @pytest.mark.parametrize("kind", [GOOGLE, GRAPH, CARDDAV])
    async def test_every_provider_takes_a_whole_series(self, kind: ConnectorType) -> None:
        client = self._client(self.occurrence, self.master)

        with _door(client, kind):
            await calendar_service.update_event(USER, _change(summary="Retro"))

        client.update_event.assert_awaited_once()

    async def test_the_master_itself_is_a_series(self) -> None:
        client = MagicMock(
            get_event=AsyncMock(return_value=self.master),
            update_event=AsyncMock(return_value=self.master),
        )

        with _door(client):
            await calendar_service.update_event(
                USER,
                EventChange.model_validate(
                    {"calendar_id": "primary", "event_id": "e1", "scope": "series", "summary": "x"}
                ),
            )

        assert client.get_event.await_count == 1
        assert client.update_event.await_args.args[0] == "e1"

    async def test_deleting_reaches_the_master(self) -> None:
        client = self._client(self.occurrence, self.master)

        with _door(client):
            await calendar_service.delete_event(
                USER, calendar_id="primary", event_id="e1_20270111", notify=None, scope="series"
            )

        assert client.delete_event.await_args.args[0] == "e1"

    async def test_an_occurrence_stays_its_own_act(self) -> None:
        client = self._client(self.occurrence, self.master)

        with _door(client):
            await calendar_service.delete_event(
                USER, calendar_id="primary", event_id="e1_20270111", notify=None
            )

        assert client.delete_event.await_args.args[0] == "e1_20270111"


class TestWhatAChangeMaySay:
    def test_a_rule_belongs_to_a_whole_series(self) -> None:
        with pytest.raises(ValidationError):
            EventChange.model_validate(
                {
                    "calendar_id": "primary",
                    "event_id": "e1",
                    "timezone": ZONE,
                    "recurrence": _spec().model_dump(mode="json"),
                }
            )

    def test_a_rule_alone_is_a_change(self) -> None:
        assert _change(recurrence=_spec().model_dump(mode="json"), timezone=ZONE)

    def test_a_rule_is_read_in_a_zone(self) -> None:
        with pytest.raises(ValidationError):
            _change(recurrence=_spec().model_dump(mode="json"))
