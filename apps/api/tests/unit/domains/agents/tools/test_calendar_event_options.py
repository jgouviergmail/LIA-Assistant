"""A reminder, free or busy, private and a call reach the assistant (ADR-369, lot 5, D2).

What the clients gained for the « Tools » section reaches the assistant in the same lot:
the model says it, the card shows it, the executor gives it to the client. An option left
out is kept as it is, on creation as on a change: nothing the person did not ask for is
written on their event.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import WORKBENCH_EVENT_REMINDER_MAX_MINUTES
from src.domains.agents.calendar.catalogue_manifests import (
    create_event_catalogue_manifest,
    update_event_catalogue_manifest,
)
from src.domains.agents.calendar.event_options import (
    ADD_CONFERENCE_UPDATE_DESCRIPTION,
    BUSY_DESCRIPTION,
    PRIVATE_DESCRIPTION,
    REMINDER_MINUTES_DESCRIPTION,
    event_options,
    readable_changes,
    readable_options,
)
from src.domains.agents.drafts.models import EventDraftInput, EventUpdateDraftInput
from src.domains.agents.tools.base import _current_runtime
from src.domains.agents.tools.calendar_draft_execution import (
    execute_event_draft,
    execute_event_update_draft,
)
from src.domains.agents.tools.calendar_tools import (
    CreateEventDraftTool,
    UpdateEventDraftTool,
    create_event_tool,
    update_event_tool,
)
from src.domains.connectors.clients.calendar_options import NO_REMINDER, EventOptions
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

USER = uuid4()
_MEETING: dict[str, Any] = {
    "id": "e1",
    "summary": "Review",
    "start": {"dateTime": "2026-11-03T10:00:00+00:00"},
    "end": {"dateTime": "2026-11-03T11:00:00+00:00"},
}


class TestWhatAnOptionReads:
    def test_what_is_not_said_is_not_written(self) -> None:
        assert readable_options({}) == {}
        assert readable_options({"reminder_minutes": None, "busy": None, "private": None}) == {}

    def test_what_is_said_is_kept_false_and_zero_included(self) -> None:
        said = {"reminder_minutes": 0, "busy": False, "private": False}

        assert readable_options(said) == said

    @pytest.mark.parametrize(
        ("minutes", "kept"),
        [
            (NO_REMINDER - 4, NO_REMINDER),
            (WORKBENCH_EVENT_REMINDER_MAX_MINUTES + 1, WORKBENCH_EVENT_REMINDER_MAX_MINUTES),
            ("30", 30),
        ],
    )
    def test_a_reminder_is_repaired_within_its_bounds(self, minutes: Any, kept: int) -> None:
        assert readable_options({"reminder_minutes": minutes}) == {"reminder_minutes": kept}

    @pytest.mark.parametrize("minutes", ["half an hour", True, 1.5, []])
    def test_a_reminder_nobody_can_read_is_no_reminder_asked(self, minutes: Any) -> None:
        assert readable_options({"reminder_minutes": minutes}) == {}

    @pytest.mark.parametrize("flag", ["busy", "private"])
    @pytest.mark.parametrize("value", ["yes", 1, 0, []])
    def test_a_switch_is_a_boolean(self, flag: str, value: Any) -> None:
        assert readable_options({flag: value}) == {}

    @pytest.mark.parametrize(("word", "read"), [("false", False), (" True ", True)])
    def test_a_switch_a_model_quoted_is_read(self, word: str, read: bool) -> None:
        assert readable_options({"busy": word}) == {"busy": read}

    def test_a_card_changed_in_words_keeps_what_is_no_option(self) -> None:
        changed = readable_changes(
            {"summary": "New", "private": "yes", "add_conference": "true", "busy": False}
        )

        assert changed == {"summary": "New", "add_conference": True, "busy": False}

    def test_a_draft_without_options_asks_the_client_nothing(self) -> None:
        assert event_options({"summary": "x", "reminder_minutes": None}) is None

    def test_a_draft_says_its_options_to_the_client(self) -> None:
        said = event_options({"reminder_minutes": 30, "busy": False, "private": True})

        assert said == EventOptions(reminder_minutes=30, busy=False, private=True)


class TestTheContractIsPublishedToBothReaders:
    @pytest.mark.parametrize(
        ("manifest", "tool"),
        [
            (create_event_catalogue_manifest, create_event_tool),
            (update_event_catalogue_manifest, update_event_tool),
        ],
    )
    @pytest.mark.parametrize(
        ("name", "wording"),
        [
            ("reminder_minutes", REMINDER_MINUTES_DESCRIPTION),
            ("busy", BUSY_DESCRIPTION),
            ("private", PRIVATE_DESCRIPTION),
        ],
    )
    def test_manifest_and_schema_read_one_description(
        self, manifest: Any, tool: Any, name: str, wording: str
    ) -> None:
        parameter = next(p for p in manifest.parameters if p.name == name)
        assert parameter.description == wording
        schema = tool.tool_call_schema.model_json_schema()
        assert schema["properties"][name]["description"] == wording

    @pytest.mark.parametrize(
        "manifest", [create_event_catalogue_manifest, update_event_catalogue_manifest]
    )
    def test_the_bounds_are_published(self, manifest: Any) -> None:
        reminder = next(p for p in manifest.parameters if p.name == "reminder_minutes")

        assert {c.kind: c.value for c in reminder.constraints} == {
            "minimum": NO_REMINDER,
            "maximum": WORKBENCH_EVENT_REMINDER_MAX_MINUTES,
        }

    def test_a_change_can_add_a_call(self) -> None:
        parameter = next(
            p for p in update_event_catalogue_manifest.parameters if p.name == "add_conference"
        )
        assert parameter.description == ADD_CONFERENCE_UPDATE_DESCRIPTION
        schema = update_event_tool.tool_call_schema.model_json_schema()
        assert schema["properties"]["add_conference"]["description"] == (
            ADD_CONFERENCE_UPDATE_DESCRIPTION
        )


class TestTheDraftCarriesThem:
    def test_the_create_draft_round_trips_them(self) -> None:
        draft = EventDraftInput(
            summary="Review",
            start_datetime="2026-11-03T10:00:00",
            end_datetime="2026-11-03T11:00:00",
            reminder_minutes=30,
            busy=False,
            private=True,
            user_language="en",
        )

        assert EventDraftInput.model_validate(draft.model_dump()) == draft
        assert draft.to_create_event_args()["reminder_minutes"] == 30

    def test_the_update_draft_keeps_none_as_keep_it(self) -> None:
        draft = EventUpdateDraftInput(event_id="e1", user_language="en")

        assert (draft.reminder_minutes, draft.busy, draft.private) == (None, None, None)
        assert draft.add_conference is False
        assert EventUpdateDraftInput.model_validate(draft.model_dump()) == draft


class TestTheToolsPrepareThem:
    async def _prepare(self, tool: Any, client: Any, **arguments: Any) -> dict[str, Any]:
        token = _current_runtime.set(
            make_tool_runtime(user_id=uuid4(), thread_id="t", store=MagicMock())
        )
        try:
            return dict(await tool.execute_api_call(client, USER, **arguments))
        finally:
            _current_runtime.reset(token)

    def _client(self) -> Any:
        client = MagicMock()
        client.get_event = AsyncMock(return_value=dict(_MEETING))
        return client

    async def test_a_new_event_carries_what_was_said(self) -> None:
        prepared = await self._prepare(
            CreateEventDraftTool(),
            self._client(),
            summary="Review",
            start_datetime="2026-11-03T10:00:00",
            end_datetime="2026-11-03T11:00:00",
            timezone="UTC",
            reminder_minutes=NO_REMINDER,
            busy=False,
            private=True,
        )

        assert prepared["reminder_minutes"] == NO_REMINDER
        assert prepared["busy"] is False
        assert prepared["private"] is True

    async def test_a_new_event_says_nothing_it_was_not_told(self) -> None:
        prepared = await self._prepare(
            CreateEventDraftTool(),
            self._client(),
            summary="Review",
            start_datetime="2026-11-03T10:00:00",
            end_datetime="2026-11-03T11:00:00",
            timezone="UTC",
        )

        assert not {"reminder_minutes", "busy", "private"} & set(prepared)

    async def test_a_change_carries_what_was_said_and_the_call(self) -> None:
        prepared = await self._prepare(
            UpdateEventDraftTool(),
            self._client(),
            event_id="e1",
            calendar_id="primary",
            timezone="UTC",
            reminder_minutes=15,
            private=False,
            add_conference=True,
        )

        assert prepared["reminder_minutes"] == 15
        assert prepared["private"] is False
        assert "busy" not in prepared
        assert prepared["add_conference"] is True

    async def test_an_event_with_a_call_keeps_it(self) -> None:
        """A second request for a call would replace the link its guests already hold."""
        client = self._client()
        client.get_event = AsyncMock(
            return_value={**_MEETING, "hangoutLink": "https://meet.google.com/abc"}
        )

        prepared = await self._prepare(
            UpdateEventDraftTool(),
            client,
            event_id="e1",
            calendar_id="primary",
            timezone="UTC",
            add_conference=True,
        )

        assert prepared["add_conference"] is False

    def test_the_draft_of_a_new_event_holds_them(self) -> None:
        tool = CreateEventDraftTool()
        output = tool.format_registry_response(
            {
                "summary": "Review",
                "start_datetime": "2026-11-03T10:00:00",
                "end_datetime": "2026-11-03T11:00:00",
                "reminder_minutes": 30,
                "busy": False,
                "private": True,
            }
        )

        content = next(iter(output.registry_updates.values())).payload["content"]
        assert content["reminder_minutes"] == 30
        assert content["busy"] is False
        assert content["private"] is True

    def test_the_draft_of_a_change_holds_them_and_the_call(self) -> None:
        tool = UpdateEventDraftTool()
        output = tool.format_registry_response(
            {"event_id": "e1", "reminder_minutes": 15, "add_conference": True}
        )

        content = next(iter(output.registry_updates.values())).payload["content"]
        assert content["reminder_minutes"] == 15
        assert content["add_conference"] is True


@contextmanager
def _the_client(method: str, answer: dict[str, Any]) -> Iterator[Any]:
    client = MagicMock()
    setattr(client, method, AsyncMock(return_value=answer))
    with (
        patch(
            "src.domains.connectors.provider_resolver.resolve_client_for_category",
            new=AsyncMock(return_value=(client, MagicMock())),
        ),
        patch(
            "src.domains.agents.tools.calendar_draft_execution._resolve_calendar_id",
            new=AsyncMock(return_value="primary"),
        ),
    ):
        yield client


class TestTheExecutorsGiveThem:
    _NEW = {
        "summary": "Review",
        "start_datetime": "2026-11-03T10:00:00",
        "end_datetime": "2026-11-03T11:00:00",
        "timezone": "UTC",
    }

    async def test_a_new_event_reaches_the_client_with_them(self) -> None:
        with _the_client("create_event", {"id": "e1"}) as client:
            await execute_event_draft(
                {**self._NEW, "reminder_minutes": 30, "busy": False}, USER, MagicMock()
            )

        assert client.create_event.call_args.kwargs["options"] == EventOptions(
            reminder_minutes=30, busy=False
        )

    async def test_an_event_nobody_said_anything_of_keeps_the_providers_default(self) -> None:
        with _the_client("create_event", {"id": "e1"}) as client:
            await execute_event_draft(dict(self._NEW), USER, MagicMock())

        assert client.create_event.call_args.kwargs["options"] is None

    async def test_a_change_reaches_the_client_with_them_and_the_call(self) -> None:
        with _the_client("update_event", {"id": "e1"}) as client:
            await execute_event_update_draft(
                {
                    "event_id": "e1",
                    "timezone": "UTC",
                    "private": True,
                    "add_conference": True,
                },
                USER,
                MagicMock(),
            )

        kwargs = client.update_event.call_args.kwargs
        assert kwargs["options"] == EventOptions(private=True)
        assert kwargs["add_conference"] is True

    async def test_only_a_link_the_provider_returned_is_claimed(self) -> None:
        with _the_client("update_event", {"id": "e1", "hangoutLink": "https://meet/x"}):
            done = await execute_event_update_draft(
                {"event_id": "e1", "timezone": "UTC", "add_conference": True}, USER, MagicMock()
            )
        with _the_client("update_event", {"id": "e1"}):
            none = await execute_event_update_draft(
                {"event_id": "e1", "timezone": "UTC", "add_conference": True}, USER, MagicMock()
            )

        assert done["conference_link"] == "https://meet/x"
        assert "conference_link" not in none
