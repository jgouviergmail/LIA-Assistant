"""The assistant answers an invitation, on any calendar (ADR-369, lot 5, D2).

What the clients gained reaches the assistant in the same lot. An answer leaves for the
organiser, so the tool drafts it: the card is the confirmation, in both execution modes.
It answers for the person alone: an event that does not name them is said, never answered.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.calendar.answer_manifest import (
    EVENT_ANSWERS,
    respond_to_event_catalogue_manifest,
)
from src.domains.agents.tools.calendar_answer_tools import RespondToEventTool
from src.domains.agents.tools.calendar_draft_execution import execute_event_answer_draft
from src.domains.agents.tools.common import ToolErrorCode

pytestmark = pytest.mark.unit

USER = uuid4()
TOOLS = "src.domains.agents.tools.calendar_answer_tools"
TEAM = "team@group.calendar.google.com"


def _client(**answers: Any) -> Any:
    client = MagicMock()
    client.respond_to_event = AsyncMock(return_value={"id": "e1"})
    client.get_event = AsyncMock(
        return_value={
            "summary": "Weekly sync",
            "start": {"dateTime": "2026-11-05T09:00:00Z"},
            "organizer": {"email": "ana@example.org"},
            "attendees": [{"email": "me@example.org", "self": True}],
        }
    )
    client.configure_mock(**answers)
    return client


class TestTheManifest:
    def test_an_answer_that_leaves_for_someone_else_is_a_card_first(self) -> None:
        assert respond_to_event_catalogue_manifest.mutation_policy == "draft"
        assert respond_to_event_catalogue_manifest.agent == "event_agent"

    def test_the_answers_are_published_as_the_tool_reads_them(self) -> None:
        response = next(
            p for p in respond_to_event_catalogue_manifest.parameters if p.name == "response"
        )
        assert tuple(response.constraints[0].value) == EVENT_ANSWERS


class TestTheCall:
    async def test_it_reads_the_invitation_and_answers_nothing_yet(self) -> None:
        client = _client()

        result = await RespondToEventTool().execute_api_call(
            client, USER, event_id="e1", response="tentative", calendar_id=TEAM
        )

        client.respond_to_event.assert_not_awaited()
        client.get_event.assert_awaited_once_with("e1", TEAM)
        assert result == {
            "event_id": "e1",
            "response": "tentative",
            "calendar_id": TEAM,
            "summary": "Weekly sync",
            "start_datetime": "2026-11-05T09:00:00Z",
            "organizer": "ana@example.org",
        }

    async def test_the_calendar_defaults_to_the_primary_one(self) -> None:
        client = _client()

        await RespondToEventTool().execute_api_call(
            client, USER, event_id="e1", response="accepted"
        )

        client.get_event.assert_awaited_once_with("e1", "primary")

    @pytest.mark.parametrize("named", [{"attendees": [{"self": True}]}, {"myResponse": "declined"}])
    async def test_the_person_is_found_on_every_provider(self, named: dict[str, Any]) -> None:
        client = _client(get_event=AsyncMock(return_value=named))

        result = await RespondToEventTool().execute_api_call(
            client, USER, event_id="e1", response="accepted"
        )

        assert "error_code" not in result

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"event_id": "", "response": "accepted"},
            {"event_id": "e1", "response": "maybe"},
            {"event_id": "e1"},
        ],
    )
    async def test_what_cannot_be_answered_is_refused_without_a_call(
        self, kwargs: dict[str, Any]
    ) -> None:
        client = _client()

        result = await RespondToEventTool().execute_api_call(client, USER, **kwargs)

        assert result["error_code"] == ToolErrorCode.INVALID_INPUT.value
        client.get_event.assert_not_awaited()

    async def test_an_event_that_does_not_name_the_person_asks_nobody_anything(self) -> None:
        client = _client(get_event=AsyncMock(return_value={"attendees": [{"email": "a@x"}]}))

        result = await RespondToEventTool().execute_api_call(
            client, USER, event_id="e1", response="accepted"
        )

        assert result["error_code"] == ToolErrorCode.CONSTRAINT_VIOLATION.value

    async def test_an_organiser_has_no_invitation_to_answer(self) -> None:
        """Google lists the organiser among the attendees, marked ``self`` like anyone."""
        event = {"organizer": {"self": True}, "attendees": [{"self": True}]}
        client = _client(get_event=AsyncMock(return_value=event))

        result = await RespondToEventTool().execute_api_call(
            client, USER, event_id="e1", response="accepted"
        )

        assert result["error_code"] == ToolErrorCode.CONSTRAINT_VIOLATION.value

    def test_a_refusal_is_a_failure(self) -> None:
        refused = RespondToEventTool().format_registry_response(
            {"error_code": "INVALID_INPUT", "message": "no"}
        )

        assert refused.success is False


class TestTheCalendar:
    async def test_a_named_calendar_is_read_and_kept_by_its_id(self) -> None:
        client = _client()
        with patch(
            f"{TOOLS}.resolve_calendar_name", AsyncMock(return_value="cal-work")
        ) as resolved:
            result = await RespondToEventTool().execute_api_call(
                client, USER, event_id="e1", response="accepted", calendar_id="Travail"
            )

        resolved.assert_awaited_once_with(client, "Travail")
        client.get_event.assert_awaited_once_with("e1", "cal-work")
        assert result["calendar_id"] == "cal-work"

    async def test_an_event_of_another_calendar_is_found_through_the_context(self) -> None:
        client = _client()
        tool = RespondToEventTool()
        tool.runtime = MagicMock()
        with (
            patch(f"{TOOLS}.validate_runtime_config", return_value=MagicMock()),
            patch(
                f"{TOOLS}.resolve_calendar_id_from_context",
                AsyncMock(return_value="cal-family"),
            ),
        ):
            result = await tool.execute_api_call(client, USER, event_id="e1", response="accepted")

        client.get_event.assert_awaited_once_with("e1", "cal-family")
        assert result["calendar_id"] == "cal-family"

    async def test_an_event_the_context_does_not_know_is_looked_for_in_the_primary(self) -> None:
        client = _client()
        tool = RespondToEventTool()
        tool.runtime = MagicMock()
        with (
            patch(f"{TOOLS}.validate_runtime_config", return_value=MagicMock()),
            patch(f"{TOOLS}.resolve_calendar_id_from_context", AsyncMock(return_value=None)),
        ):
            await tool.execute_api_call(client, USER, event_id="e1", response="accepted")

        client.get_event.assert_awaited_once_with("e1", "primary")


class TestTheConfirmedAnswer:
    @pytest.mark.parametrize("stored", ["peut-être", "", None])
    async def test_an_answer_off_the_vocabulary_never_leaves(self, stored: str | None) -> None:
        client = _client()
        with (
            patch(
                "src.domains.connectors.provider_resolver.resolve_client_for_category",
                AsyncMock(return_value=(client, "google_calendar")),
            ),
            pytest.raises(ValueError),
        ):
            await execute_event_answer_draft(
                {"event_id": "e1", "response": stored}, USER, MagicMock()
            )

        client.respond_to_event.assert_not_awaited()

    async def test_it_leaves_once_confirmed(self) -> None:
        client = _client()
        with patch(
            "src.domains.connectors.provider_resolver.resolve_client_for_category",
            AsyncMock(return_value=(client, "google_calendar")),
        ):
            result = await execute_event_answer_draft(
                {"event_id": "e1", "response": "declined", "calendar_id": "work"},
                USER,
                MagicMock(),
            )

        client.respond_to_event.assert_awaited_once_with("e1", "declined", "work")
        assert result["success"] is True
