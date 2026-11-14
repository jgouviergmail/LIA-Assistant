"""The assistant's tasks tools across the account's lists (owner rule, 2026-11-10).

Reading takes every list unless one is named, in one order across them, and says what it could
not read. A new task goes in the default list unless one is named, and its card says where. A
task that exists is fetched, completed, changed and deleted in its OWN list.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import httpx
import pytest
from langgraph.store.memory import InMemoryStore

from src.core.config import get_settings
from src.core.constants import SUPPORTED_LANGUAGES
from src.core.exceptions import ConnectorAPIError
from src.core.field_names import FIELD_TASK_LIST_ID, FIELD_TASK_LIST_NAME
from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.tasks.catalogue_manifests import (
    create_task_catalogue_manifest,
    get_tasks_catalogue_manifest,
)
from src.domains.agents.tasks.parameter_descriptions import (
    TASK_LIST_GET_DESCRIPTION,
    TASK_LIST_NEW_DESCRIPTION,
    TASK_LIST_OF_TASK_DESCRIPTION,
)
from src.domains.agents.tools import task_list_scope as scope
from src.domains.agents.tools import tasks_tools
from src.domains.agents.tools.exceptions import ToolValidationError
from src.domains.agents.tools.tasks_tools import (
    CompleteTaskTool,
    CreateTaskDraftTool,
    DeleteTaskDraftTool,
    GetTaskDetailsTool,
    ListTasksTool,
    UpdateTaskDraftTool,
    create_task_tool,
    get_tasks_tool,
)
from src.domains.connectors.models import ConnectorType
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

USER = uuid4()
_SOON, _LATER = "2026-11-12T00:00:00.000Z", "2026-11-20T00:00:00.000Z"


def _task(task_id: str, due: str | None = None, **fields: Any) -> dict[str, Any]:
    return {"id": task_id, "title": task_id, **({"due": due} if due else {}), **fields}


def _client(pages: dict[str, Any] | None = None, **methods: Any) -> MagicMock:
    """An account whose lists (``l1`` is « L1 ») hold these tasks, or fail."""
    held: dict[str, Any] = {"l1": [], "l2": []} if pages is None else pages

    async def read(list_id: str, **_kwargs: Any) -> dict[str, Any]:
        answer = held[list_id]
        if isinstance(answer, Exception):
            raise answer
        return {"items": [dict(task) for task in answer], "next_page_token": None}

    client = MagicMock(connector_type=ConnectorType.GOOGLE_TASKS)
    client.list_tasks = AsyncMock(side_effect=read)
    client.list_task_lists = AsyncMock(
        return_value={"items": [{"id": key, "title": key.upper()} for key in held]}
    )
    for name, value in methods.items():
        setattr(
            client, name, value if isinstance(value, AsyncMock) else AsyncMock(return_value=value)
        )
    return client


def _preferences(tool: Any) -> Any:
    return patch.object(tool, "get_user_preferences_safe", AsyncMock(return_value=("UTC", "en")))


async def _read(client: MagicMock, **asked: Any) -> tuple[ListTasksTool, dict[str, Any]]:
    tool = ListTasksTool()
    with _preferences(tool):
        return tool, await tool.execute_api_call(client, USER, **asked)


def _ids(result: dict[str, Any]) -> list[str]:
    return [task["id"] for task in result["tasks"]]


class TestReading:
    async def test_every_list_is_read_in_one_order_when_none_is_named(self) -> None:
        client = _client(
            {"l1": [_task("later", _LATER), _task("undated")], "l2": [_task("soon", _SOON)]}
        )

        _tool, result = await _read(client)

        assert _ids(result) == ["soon", "later", "undated"]
        assert result["task_list_id"] is None
        assert result["partial_note"] == ""

    async def test_the_list_named_is_read_alone_in_its_own_order(self) -> None:
        client = _client(
            {"l1": [_task("a", _SOON)], "l2": [_task("later", _LATER), _task("soon", _SOON)]}
        )

        _tool, result = await _read(client, task_list_id="L2")

        assert _ids(result) == ["later", "soon"], "the person's own order in that list"
        assert result["task_list_id"] == "l2"
        assert [asked.args[0] for asked in client.list_tasks.await_args_list] == ["l2"]

    async def test_a_list_nobody_has_reads_nothing_rather_than_another_list(self) -> None:
        client = _client({"l1": [_task("a")]})

        with pytest.raises(ToolValidationError):
            await _read(client, task_list_id="Work")

        client.list_tasks.assert_not_awaited()

    async def test_a_list_that_could_not_be_read_is_named_to_the_model(self) -> None:
        client = _client({"l1": [_task("a")], "l2": httpx.ConnectError("down")})

        tool, result = await _read(client)
        output = tool.format_registry_response(result)

        assert _ids(result) == ["a"]
        assert "L2" in result["partial_note"]
        assert output.message.endswith(result["partial_note"])
        assert output.structured_data["partial_note"] == result["partial_note"]

    async def test_an_answer_cut_at_its_size_says_more_exist(self) -> None:
        cap = get_settings().tasks_tool_default_max_results
        tasks = [_task(f"t{index}") for index in range(cap)]
        client = _client({"l1": tasks, "l2": [_task("one-more")]})

        _tool, result = await _read(client)

        assert len(result["tasks"]) == cap
        assert result["partial_note"].startswith("More tasks exist")

    async def test_a_whole_read_adds_no_note_to_the_answer(self) -> None:
        tool, result = await _read(_client({"l1": [_task("a")], "l2": []}))

        output = tool.format_registry_response(result)

        assert "partial_note" not in output.structured_data
        assert "More tasks exist" not in output.message

    async def test_each_task_reaches_the_answer_with_its_own_list(self) -> None:
        tool, result = await _read(_client({"l1": [_task("a")], "l2": [_task("b")]}))

        output = tool.format_registry_response(result)

        carried = {
            item.payload["id"]: (
                item.payload[FIELD_TASK_LIST_ID],
                item.payload[FIELD_TASK_LIST_NAME],
            )
            for item in output.registry_updates.values()
        }
        assert carried == {"a": ("l1", "L1"), "b": ("l2", "L2")}

    async def test_only_what_is_done_is_kept_when_asked(self) -> None:
        client = _client(
            {
                "l1": [_task("done", status="completed"), _task("open", status="needsAction")],
                "l2": [],
            }
        )

        _tool, result = await _read(client, only_completed=True)

        assert _ids(result) == ["done"]
        asked = client.list_tasks.await_args_list[0].kwargs
        assert (asked["show_completed"], asked["show_hidden"]) == (True, True)


class TestFetchingTasksThatExist:
    def _lists(self, lists: dict[str, str]) -> Any:
        return patch.object(tasks_tools, "task_list_ids_of", AsyncMock(return_value=lists))

    async def test_each_task_of_a_batch_is_fetched_in_its_own_list(self) -> None:
        client = _client(get_task=AsyncMock(side_effect=lambda _list, task_id: _task(task_id)))
        tool = GetTaskDetailsTool()
        runtime = make_tool_runtime(store=InMemoryStore())
        tool.runtime = runtime

        with self._lists({"t1": "l1", "t2": "l2"}) as resolved, _preferences(tool):
            result = await tool.execute_api_call(client, USER, task_ids=["t1", "t2"])

        assert client.get_task.await_args_list == [call("l1", "t1"), call("l2", "t2")]
        assert {task["id"]: task[FIELD_TASK_LIST_ID] for task in result["tasks"]} == {
            "t1": "l1",
            "t2": "l2",
        }
        assert resolved.await_args.kwargs["runtime"] is runtime, "the tool's own runtime"

    async def test_one_task_is_fetched_in_its_own_list(self) -> None:
        client = _client(get_task=_task("t1"))
        tool = GetTaskDetailsTool()
        found = patch.object(tasks_tools, "task_list_id_of", AsyncMock(return_value="l2"))

        with found, _preferences(tool):
            result = await tool.execute_api_call(client, USER, task_id="t1")

        client.get_task.assert_awaited_once_with("l2", "t1")
        assert result["task_list_id"] == "l2"

    async def test_a_task_of_a_batch_no_list_holds_is_said_and_the_others_are_fetched(
        self,
    ) -> None:
        client = _client(get_task=AsyncMock(side_effect=lambda _list, task_id: _task(task_id)))
        tool = GetTaskDetailsTool()

        with self._lists({"t1": "l1"}), _preferences(tool):
            result = await tool.execute_api_call(client, USER, task_ids=["t1", "gone"])

        assert [task["id"] for task in result["tasks"]] == ["t1"]
        assert result["errors"] == [{"task_id": "gone", "error": scope.UNKNOWN_TASK}]
        client.get_task.assert_awaited_once_with("l1", "t1")


def _default(list_id: str = "l2") -> Any:
    return patch.object(scope, "default_task_list_id", AsyncMock(return_value=list_id))


class TestCreating:
    async def _prepared(self, client: MagicMock, **asked: Any) -> dict[str, Any]:
        return await CreateTaskDraftTool().execute_api_call(client, USER, title="Pay", **asked)

    async def test_a_new_task_goes_in_the_default_list_when_nobody_names_one(self) -> None:
        client = _client(get_task_list={"id": "l2", "title": "L2"})

        with _default():
            prepared = await self._prepared(client)

        assert (prepared["task_list_id"], prepared["task_list_name"]) == ("l2", "L2")

    @pytest.mark.parametrize("given", ["l1", "L1"])
    async def test_it_goes_in_the_list_named_by_its_id_or_its_name(self, given: str) -> None:
        with _default() as default:
            prepared = await self._prepared(_client(), task_list_id=given)

        assert (prepared["task_list_id"], prepared["task_list_name"]) == ("l1", "L1")
        default.assert_not_awaited()

    async def test_a_list_nobody_has_creates_nothing_rather_than_elsewhere(self) -> None:
        """Measured 2026-11-10: a mistyped list became the provider's default one in silence."""
        with _default(), pytest.raises(ToolValidationError):
            await self._prepared(_client(), task_list_id="Work")

    async def test_the_draft_keeps_where_it_goes(self) -> None:
        with _default():
            prepared = await self._prepared(_client(), task_list_id="l1")
        tool = CreateTaskDraftTool()

        with patch.object(tool, "get_user_language", return_value="en"):
            output = tool.format_registry_response(prepared)

        [draft] = output.registry_updates.values()
        content = draft.payload["content"]
        assert (content["task_list_id"], content["task_list_name"]) == ("l1", "L1")

    @pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
    def test_the_card_names_the_list_in_every_language(self, language: str) -> None:
        label = get_draft_preview_labels(language)["task_list"]
        content = {"title": "Pay", "task_list_id": "l1", "task_list_name": "Household"}

        card = Draft(type=DraftType.TASK, content=content).get_detailed_preview(language, "UTC")

        assert label and label != "task_list"
        assert label in card and "Household" in card

    def test_a_card_without_a_list_s_name_shows_no_empty_row(self) -> None:
        label = get_draft_preview_labels("en")["task_list"]

        card = Draft(type=DraftType.TASK, content={"title": "Pay"}).get_detailed_preview(
            "en", "UTC"
        )

        assert label not in card


class TestActingOnATaskThatExists:
    """Completed, changed, deleted where the conversation read it, not in the default list."""

    def _known(self, lists: dict[str, str]) -> Any:
        return patch.object(scope, "looked_up_task_list_ids", AsyncMock(return_value=lists))

    async def test_it_is_completed_in_its_own_list_found_with_the_tool_s_runtime(self) -> None:
        client = _client(complete_task=_task("t1"))
        tool = CompleteTaskTool()
        runtime = make_tool_runtime(store=InMemoryStore())
        tool.runtime = runtime

        with self._known({"t1": "l2"}) as known, _default("l1"):
            await tool.execute_api_call(client, USER, task_id="t1")

        client.complete_task.assert_awaited_once_with("l2", "t1")
        known.assert_awaited_once_with(runtime, "complete_task_tool")

    async def test_the_list_named_wins_over_what_the_conversation_read(self) -> None:
        client = _client(complete_task=_task("t1"))

        with self._known({"t1": "l2"}), _default():
            await CompleteTaskTool().execute_api_call(client, USER, task_id="t1", task_list_id="L1")

        client.complete_task.assert_awaited_once_with("l1", "t1")

    async def test_a_task_nobody_read_is_searched_in_every_list(self) -> None:
        """Not assumed in the default list: asked of each, completed where it lives."""

        async def holds(list_id: str, task_id: str) -> dict[str, Any]:
            if list_id != "l2":
                raise ConnectorAPIError(connector_type="google_tasks", status_code=404, detail="no")
            return _task(task_id)

        client = _client(complete_task=_task("t1"), get_task=AsyncMock(side_effect=holds))

        with self._known({}), _default("l1"):
            await CompleteTaskTool().execute_api_call(client, USER, task_id="t1")

        client.complete_task.assert_awaited_once_with("l2", "t1")

    async def test_a_task_no_list_holds_is_refused_and_nothing_is_completed(self) -> None:
        nowhere = AsyncMock(
            side_effect=ConnectorAPIError(
                connector_type="google_tasks", status_code=404, detail="no"
            )
        )
        client = _client(complete_task=_task("t1"), get_task=nowhere)

        with self._known({}), _default("l1"), pytest.raises(ToolValidationError) as refused:
            await CompleteTaskTool().execute_api_call(client, USER, task_id="gone")

        assert str(refused.value) == scope.UNKNOWN_TASK
        client.complete_task.assert_not_awaited()

    async def test_a_change_is_drafted_in_its_own_list(self) -> None:
        client = _client(get_task=_task("t1"))
        tool = UpdateTaskDraftTool()

        with self._known({"t1": "l2"}), _default("l1"), _preferences(tool):
            prepared = await tool.execute_api_call(client, USER, task_id="t1", title="New")

        client.get_task.assert_awaited_once_with("l2", "t1")
        assert prepared["task_list_id"] == "l2"

    async def test_a_deletion_is_drafted_in_its_own_list(self) -> None:
        client = _client(get_task=_task("t1"))

        with self._known({"t1": "l2"}), _default("l1"):
            prepared = await DeleteTaskDraftTool().execute_api_call(client, USER, task_id="t1")

        client.get_task.assert_awaited_once_with("l2", "t1")
        assert prepared["task_list_id"] == "l2"


class TestWhatTheModelIsTold:
    """One wording for the planner's manifest and the loop's tool schema (ADR-184)."""

    @staticmethod
    def _manifest_wording(manifest: Any) -> str:
        return next(p.description for p in manifest.parameters if p.name == scope.LIST_PARAMETER)

    @staticmethod
    def _schema_wording(tool: Any) -> str:
        schema = tool.tool_call_schema.model_json_schema()
        return str(schema["properties"][scope.LIST_PARAMETER]["description"])

    def test_reading_says_every_list_unless_one_is_named(self) -> None:
        assert self._manifest_wording(get_tasks_catalogue_manifest) == TASK_LIST_GET_DESCRIPTION
        assert self._schema_wording(get_tasks_tool) == TASK_LIST_GET_DESCRIPTION
        assert "every list" in TASK_LIST_GET_DESCRIPTION

    def test_a_task_s_own_list_may_be_left_out_wherever_it_is_asked(self) -> None:
        """« Omit when unknown » is told of a parameter the model CAN omit, move included."""
        from src.domains.agents.tasks.organize_manifest import move_task_catalogue_manifest
        from src.domains.agents.tools.task_organize_tools import move_task_tool

        source = next(
            p for p in move_task_catalogue_manifest.parameters if p.name == scope.LIST_PARAMETER
        )
        schema = move_task_tool.tool_call_schema.model_json_schema()

        assert source.description == TASK_LIST_OF_TASK_DESCRIPTION
        assert source.required is False
        assert scope.LIST_PARAMETER not in schema.get("required", [])
        assert "destination_list_id" in schema["required"]

    def test_creating_says_the_default_list_unless_one_is_named(self) -> None:
        assert self._manifest_wording(create_task_catalogue_manifest) == TASK_LIST_NEW_DESCRIPTION
        assert self._schema_wording(create_task_tool) == TASK_LIST_NEW_DESCRIPTION

    def test_no_list_parameter_defaults_to_the_provider_s_alias(self) -> None:
        """A default the schema fills in reads as a list the model named."""
        for tool in (get_tasks_tool, create_task_tool):
            schema = tool.tool_call_schema.model_json_schema()
            assert schema["properties"][scope.LIST_PARAMETER].get("default") is None

    def test_the_planner_can_read_each_task_s_list_to_act_on_it(self) -> None:
        paths = {output.path for output in get_tasks_catalogue_manifest.outputs}

        assert {f"tasks[].{FIELD_TASK_LIST_ID}", f"tasks[].{FIELD_TASK_LIST_NAME}"} <= paths
