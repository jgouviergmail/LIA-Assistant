"""What the assistant gains with the tasks screen (ADR-369, lot 9, D2).

It renames a list and moves a task, each undone by one more call. On To Do it writes steps, an
importance, a reminder and a repetition, shown on the card and carried at execution; on Google,
which keeps none of them, it is told so rather than left to promise what would be dropped.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.exceptions import ToolValidationError
from src.domains.agents.tools.task_extras import TaskExtras, extras_refusal, read_extras
from src.domains.agents.tools.task_organize_tools import MoveTaskTool, RenameTaskListTool
from src.domains.agents.tools.tasks_draft_executors import (
    execute_task_draft,
    execute_task_update_draft,
)
from src.domains.connectors.clients.task_details import TaskDetails, TaskLeftBehindError
from src.domains.connectors.models import ConnectorType

pytestmark = pytest.mark.unit

USER = uuid4()
TODO, GOOGLE = ConnectorType.MICROSOFT_TASKS, ConnectorType.GOOGLE_TASKS


#: The account's lists: a tool takes one by its id or by its name (owner rule, 2026-11-10).
_LISTS = {"items": [{"id": "l1", "title": "Bills"}, {"id": "l2", "title": "Home"}]}


def _client(kind: ConnectorType = TODO, **methods: Any) -> MagicMock:
    client = MagicMock(connector_type=kind)
    for name, value in {"list_task_lists": _LISTS, **methods}.items():
        setattr(client, name, AsyncMock(return_value=value))
    return client


def _card(kind: DraftType, content: dict[str, Any]) -> str:
    return Draft(type=kind, content=content).get_detailed_preview("en", "UTC")


class TestRenamingAList:
    async def test_it_is_renamed(self) -> None:
        client = _client(rename_task_list={"id": "l1", "title": "New"})

        result = await RenameTaskListTool().execute_api_call(
            client, USER, task_list_id="l1", title="New"
        )

        client.rename_task_list.assert_awaited_once_with("l1", "New")
        assert result["title"] == "New"

    async def test_the_list_is_taken_by_its_name_too(self) -> None:
        client = _client(rename_task_list={"id": "l2", "title": "House"})

        result = await RenameTaskListTool().execute_api_call(
            client, USER, task_list_id="home", title="House"
        )

        client.rename_task_list.assert_awaited_once_with("l2", "House")
        assert result["task_list_id"] == "l2"

    async def test_a_list_nobody_has_is_refused_never_replaced_by_another(self) -> None:
        client = _client(rename_task_list={})

        with pytest.raises(ToolValidationError):
            await RenameTaskListTool().execute_api_call(
                client, USER, task_list_id="l9", title="New"
            )

        client.rename_task_list.assert_not_awaited()

    async def test_a_name_is_needed(self) -> None:
        with pytest.raises(Exception):  # noqa: B017 - the tool's own validation
            await RenameTaskListTool().execute_api_call(_client(), USER, task_list_id="l1")


class TestMovingATask:
    async def test_it_goes_and_says_what_it_is_called_now(self) -> None:
        client = _client(move_task={"id": "n1", "title": "Pay"})

        result = await MoveTaskTool().execute_api_call(
            client, USER, task_id="t1", task_list_id="l1", destination_list_id="l2"
        )

        client.move_task.assert_awaited_once_with("l1", "t1", "l2")
        assert result["task_id"] == "n1"

    async def test_both_lists_are_taken_by_their_names_too(self) -> None:
        client = _client(move_task={"id": "n1", "title": "Pay"})

        result = await MoveTaskTool().execute_api_call(
            client, USER, task_id="t1", task_list_id="Bills", destination_list_id="home"
        )

        client.move_task.assert_awaited_once_with("l1", "t1", "l2")
        assert result["task_list_id"] == "l2"

    async def test_a_destination_nobody_has_moves_nothing(self) -> None:
        client = _client(move_task={})

        with pytest.raises(ToolValidationError):
            await MoveTaskTool().execute_api_call(
                client, USER, task_id="t1", task_list_id="l1", destination_list_id="Work"
            )

        client.move_task.assert_not_awaited()

    async def test_a_task_left_in_both_lists_is_said_as_a_failure(self) -> None:
        client = _client()
        client.move_task = AsyncMock(side_effect=TaskLeftBehindError)

        result = await MoveTaskTool().execute_api_call(
            client, USER, task_id="t1", task_list_id="l1", destination_list_id="l2"
        )

        assert result["error_code"] == ToolErrorCode.CONFLICT.value

    async def test_a_list_is_no_move_to_itself(self) -> None:
        client = _client(move_task={})

        result = await MoveTaskTool().execute_api_call(
            client, USER, task_id="t1", task_list_id="l1", destination_list_id="l1"
        )

        assert result["error_code"] == ToolErrorCode.INVALID_INPUT.value
        client.move_task.assert_not_awaited()


class TestWhatGoogleKeepsNot:
    @pytest.mark.parametrize(
        "asked",
        [
            {"importance": "high"},
            {"reminder": "2027-01-10T09:00:00Z"},
            {"repeat": "weekly"},
            {"steps": ["One"]},
            {"clear_reminder": True},
        ],
    )
    def test_each_is_refused_by_name(self, asked: dict[str, Any]) -> None:
        refusal = extras_refusal(_client(GOOGLE), read_extras(asked), has_due=True)

        assert refusal is not None
        assert refusal["error_code"] == ToolErrorCode.INVALID_INPUT.value

    def test_nothing_asked_is_nothing_refused(self) -> None:
        assert extras_refusal(_client(GOOGLE), read_extras({}), has_due=False) is None

    def test_a_repetition_needs_a_day(self) -> None:
        refusal = extras_refusal(_client(TODO), read_extras({"repeat": "daily"}), has_due=False)

        assert refusal is not None

    def test_to_do_takes_them(self) -> None:
        extras = read_extras({"importance": "high", "repeat": "daily", "steps": ["One"]})

        assert extras_refusal(_client(TODO), extras, has_due=True) is None

    @pytest.mark.parametrize("asked", [{"importance": "urgent"}, {"repeat": "hourly"}])
    def test_a_word_it_cannot_read_is_refused(self, asked: dict[str, Any]) -> None:
        assert extras_refusal(_client(TODO), read_extras(asked), has_due=True) is not None


class TestTheCard:
    def test_a_new_task_shows_what_it_will_hold(self) -> None:
        shown = _card(
            DraftType.TASK,
            {
                "title": "Pay",
                "importance": "high",
                "reminder": "2027-01-10T09:00:00Z",
                "repeat": "weekly",
                "steps": ["One", "Two"],
            },
        )

        assert "High" in shown
        assert "Every week" in shown
        assert "One" in shown and "Two" in shown

    def test_a_task_with_none_of_it_shows_none_of_it(self) -> None:
        shown = _card(DraftType.TASK, {"title": "Pay"})

        assert "Importance" not in shown and "Repeats" not in shown and "Steps" not in shown

    def test_a_change_says_what_it_takes_off(self) -> None:
        shown = _card(
            DraftType.TASK_UPDATE,
            {"task_id": "t1", "title": "Pay", "clear_reminder": True, "clear_repeat": True},
        )

        assert shown.count("removed") == 2


class TestExecution:
    def _resolving(self, client: MagicMock) -> Any:
        return patch(
            "src.domains.agents.tools.tasks_draft_executors._resolve_tasks_client",
            AsyncMock(return_value=client),
        )

    async def test_a_confirmed_task_carries_them(self) -> None:
        client = _client(create_task={"id": "t1"})

        with self._resolving(client):
            await execute_task_draft(
                {
                    "title": "Pay",
                    "due": "2027-01-11T00:00:00Z",
                    "importance": "high",
                    "reminder": "2027-01-10T09:00:00Z",
                    "repeat": "weekly",
                    "steps": ["One"],
                },
                USER,
                MagicMock(),
            )

        kwargs = client.create_task.await_args.kwargs
        assert kwargs["details"] == TaskDetails(
            importance="high",
            reminder=datetime(2027, 1, 10, 9, 0, tzinfo=UTC),
            repeat="weekly",
            repeat_from=date(2027, 1, 11),
        )
        assert kwargs["steps"] == ("One",)

    async def test_a_plain_task_carries_nothing_of_the_kind(self) -> None:
        client = _client(create_task={"id": "t1"})

        with self._resolving(client):
            await execute_task_draft({"title": "Pay"}, USER, MagicMock())

        assert client.create_task.await_args.kwargs["details"] is None

    async def test_a_confirmed_change_takes_off_what_it_said(self) -> None:
        client = _client(update_task={"id": "t1", "title": "Pay"})

        with self._resolving(client):
            await execute_task_update_draft(
                {"task_id": "t1", "clear_reminder": True, "clear_repeat": True},
                USER,
                MagicMock(),
            )

        details = client.update_task.await_args.kwargs["details"]
        assert details.clear_reminder is True and details.clear_repeat is True


class TestTheExtras:
    def test_they_travel_as_the_draft_holds_them(self) -> None:
        extras = TaskExtras(importance="low", reminder=None, repeat=None, steps=("One",))

        assert extras.fields()["importance"] == "low"
        assert extras.fields()["steps"] == ["One"]
