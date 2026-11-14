"""What the assistant does with a repeating event (ADR-369, lot 10, D2).

It creates a series, in the words every recurrence of LIA is dictated in, and reaches a whole
series when the person asks for it. The rule is shown on the card in the person's language before
anyone confirms, and carried at execution; a first day the rule does not serve is refused with
the reason, so the model corrects its own call.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.recurrence import RecurrenceSpec
from src.domains.agents.calendar.event_options import event_options
from src.domains.agents.calendar.event_series import (
    EVENT_REPEAT_PARAMETERS,
    EVENT_SCOPE_PARAMETER,
    readable_series,
)
from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.tools.calendar_draft_execution import (
    execute_event_delete_draft,
    execute_event_update_draft,
)
from src.domains.agents.tools.calendar_series import read_recurrence
from src.domains.agents.tools.calendar_tools import (
    create_event_tool,
    delete_event_tool,
    update_event_tool,
)
from src.domains.agents.tools.common import ToolErrorCode

pytestmark = pytest.mark.unit

USER = uuid4()
ZONE = "Europe/Paris"
MONDAY = "2027-01-04T09:00:00"


def _card(kind: DraftType, content: dict[str, Any]) -> str:
    return Draft(type=kind, content=content).get_detailed_preview("en", "UTC")


def _resolving(client: MagicMock) -> Any:
    return patch(
        "src.domains.connectors.provider_resolver.resolve_client_for_category",
        AsyncMock(return_value=(client, MagicMock())),
    )


class TestReadingARule:
    def test_nothing_said_is_nothing_read(self) -> None:
        assert read_recurrence({}, MONDAY, ZONE, "en") == (None, None, None)

    def test_a_one_off_is_no_series(self) -> None:
        assert read_recurrence({"repeat": "once"}, MONDAY, ZONE, "en") == (None, None, None)

    def test_a_rule_is_anchored_on_the_event_and_said_in_the_person_s_language(self) -> None:
        spec, sentence, refused = read_recurrence(
            {"repeat": "weekly", "weekdays": [1], "max_occurrences": 3}, MONDAY, ZONE, "fr"
        )

        assert refused is None
        assert spec is not None
        assert RecurrenceSpec.model_validate(spec).anchor_date.isoformat() == "2027-01-04"
        assert sentence and "lundi" in sentence

    @pytest.mark.parametrize(
        ("said", "field", "value"),
        [
            ({"repeat": "weekly"}, "byweekday", [1]),
            ({"repeat": "monthly"}, "bymonthday", [4]),
            ({"repeat": "yearly"}, "bymonth", [1]),
        ],
    )
    def test_a_rhythm_with_no_day_takes_the_event_s_own(
        self, said: dict[str, Any], field: str, value: list[int]
    ) -> None:
        spec, _, refused = read_recurrence(said, MONDAY, ZONE, "en")

        assert refused is None
        assert spec is not None
        assert spec[field] == value

    def test_a_first_day_the_rule_skips_is_refused_with_the_reason(self) -> None:
        _, _, refused = read_recurrence({"repeat": "weekly", "weekdays": [3]}, MONDAY, ZONE, "en")

        assert refused is not None
        assert refused["error_code"] == ToolErrorCode.INVALID_INPUT.value
        assert "first" in refused["message"]

    def test_a_rule_that_makes_no_sense_is_refused_never_guessed(self) -> None:
        _, _, refused = read_recurrence({"repeat": "sometimes"}, MONDAY, ZONE, "en")

        assert refused is not None
        assert refused["error_code"] == ToolErrorCode.INVALID_INPUT.value


class TestWhatADraftAsks:
    def test_a_rule_reaches_the_client_with_its_zone(self) -> None:
        spec, _, _ = read_recurrence({"repeat": "daily"}, MONDAY, ZONE, "en")

        options = event_options({"recurrence": spec, "timezone": ZONE, "all_day": True})

        assert options is not None
        assert options.recurrence is not None
        assert options.zone == ZONE
        assert options.all_day is True

    def test_a_draft_with_none_asks_nothing(self) -> None:
        assert event_options({"timezone": ZONE}) is None


class TestTheCard:
    def test_a_new_series_says_when_it_comes_back(self) -> None:
        shown = _card(
            DraftType.EVENT,
            {
                "summary": "Standup",
                "start_datetime": MONDAY,
                "end_datetime": "2027-01-04T09:30:00",
                "recurrence_text": "every Monday",
            },
        )

        assert "every Monday" in shown

    @pytest.mark.parametrize("kind", [DraftType.EVENT_UPDATE, DraftType.EVENT_DELETE])
    def test_a_whole_series_is_said_before_anyone_confirms(self, kind: DraftType) -> None:
        shown = _card(
            kind,
            {"event_id": "e1", "scope": "series", "event": {}, "current_event": {}},
        )

        assert "Whole series" in shown

    def test_an_occurrence_says_nothing_of_the_kind(self) -> None:
        shown = _card(DraftType.EVENT_DELETE, {"event_id": "e1", "event": {}, "current_event": {}})

        assert "Whole series" not in shown


class TestExecution:
    occurrence = {
        "id": "e1_1",
        "recurringEventId": "e1",
        "start": {"dateTime": "2027-01-11T09:00:00+01:00"},
    }
    master = {"id": "e1", "start": {"dateTime": "2027-01-04T09:00:00+01:00"}}

    def _client(self) -> MagicMock:
        answers = {"e1_1": self.occurrence, "e1": self.master}
        return MagicMock(
            get_event=AsyncMock(side_effect=lambda event_id, calendar_id: answers[event_id]),
            update_event=AsyncMock(return_value={"id": "e1", "summary": "Retro"}),
            delete_event=AsyncMock(return_value={}),
        )

    def _calendar(self) -> Any:
        return patch(
            "src.domains.agents.tools.calendar_draft_execution._resolve_calendar_id",
            AsyncMock(return_value="primary"),
        )

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            ("2027-01-11T10:15:00", "2027-01-11T11:00:00"),
            # The tool hands its times re-localised, with the zone's own offset.
            ("2027-01-11T10:15:00+01:00", "2027-01-11T11:00:00+01:00"),
        ],
    )
    async def test_a_change_reaches_the_series_and_keeps_its_first_day(
        self, start: str, end: str
    ) -> None:
        client = self._client()

        with _resolving(client), self._calendar():
            await execute_event_update_draft(
                {
                    "event_id": "e1_1",
                    "scope": "series",
                    "moves_series": True,
                    "summary": "Retro",
                    "start_datetime": start,
                    "end_datetime": end,
                    "timezone": ZONE,
                },
                USER,
                MagicMock(),
            )

        kwargs = client.update_event.await_args.kwargs
        assert kwargs["event_id"] == "e1"
        bounds = kwargs["bounds"]
        # The series' first day, the occurrence's times, on the person's own wall.
        assert (bounds.start.iso(), bounds.end.iso()) == (
            "2027-01-04T10:15:00",
            "2027-01-04T11:00:00",
        )
        assert (bounds.start.zone.key, bounds.end.zone.key) == (ZONE, ZONE)

    async def test_a_series_renamed_keeps_its_times_out_of_the_request(self) -> None:
        client = self._client()

        with _resolving(client), self._calendar():
            await execute_event_update_draft(
                {
                    "event_id": "e1_1",
                    "scope": "series",
                    "summary": "Retro",
                    "start_datetime": "2027-01-11T09:00:00",
                    "end_datetime": "2027-01-11T09:30:00",
                    "timezone": ZONE,
                },
                USER,
                MagicMock(),
            )

        kwargs = client.update_event.await_args.kwargs
        assert kwargs["event_id"] == "e1"
        assert kwargs["bounds"] is None

    async def test_a_change_of_an_occurrence_stays_one(self) -> None:
        client = self._client()

        with _resolving(client), self._calendar():
            await execute_event_update_draft(
                {"event_id": "e1_1", "summary": "Retro", "timezone": ZONE}, USER, MagicMock()
            )

        assert client.update_event.await_args.kwargs["event_id"] == "e1_1"
        client.get_event.assert_not_awaited()

    async def test_a_deletion_reaches_the_series(self) -> None:
        client = self._client()

        with _resolving(client), self._calendar():
            await execute_event_delete_draft(
                {"event_id": "e1_1", "scope": "series"}, USER, MagicMock()
            )

        assert client.delete_event.await_args.kwargs["event_id"] == "e1"


class TestWhatADraftKeeps:
    def test_a_move_is_said_only_when_it_was_asked(self) -> None:
        assert readable_series({"scope": "series", "moves_series": True}) == {
            "scope": "series",
            "moves_series": True,
        }
        assert readable_series({"scope": "series"}) == {"scope": "series"}


class TestItsWords:
    def test_a_new_event_s_manifest_and_schema_offer_the_rule(self) -> None:
        offered = create_event_tool.tool_call_schema.model_json_schema()["properties"]

        assert {item.name for item in EVENT_REPEAT_PARAMETERS} <= set(offered)

    @pytest.mark.parametrize("tool", [update_event_tool, delete_event_tool])
    def test_a_change_and_a_deletion_offer_the_scope(self, tool: Any) -> None:
        offered = tool.tool_call_schema.model_json_schema()["properties"]

        assert offered["scope"]["description"] == EVENT_SCOPE_PARAMETER.description
