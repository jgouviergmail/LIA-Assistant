"""Which list a tasks tool works in (owner rule, 2026-11-10).

A list the model names is that list or a refusal, never another one. The default list is where
a NEW task goes when nobody names one, and nothing else. A task that exists is acted on in its
OWN list: the one named, else the one the conversation last looked it up in, else the one that
holds it — every list is asked, and a task no list holds is said, never acted on elsewhere.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.tools import StructuredTool
from langgraph.store.memory import InMemoryStore

from src.core.constants import TASK_LIST_NAMES_SCAN_MAX
from src.core.exceptions import ConnectorAPIError, ResourceNotFoundError
from src.core.field_names import FIELD_TASK_LIST_ID
from src.domains.agents.constants import CONTEXT_DOMAIN_TASKS
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.tools import task_list_scope as scope
from src.domains.agents.tools.exceptions import ToolValidationError
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.tasks_tools import get_tasks_tool
from src.domains.connectors.models import ConnectorType
from tests.helpers.runtime_context import (
    installed_runtime_context,
    make_runtime_context,
    make_tool_runtime,
)

pytestmark = pytest.mark.unit

USER = uuid4()
#: Two lists sharing a name but for its case, one with no id: what a real account may hold.
_LISTS: list[dict[str, Any]] = [
    {"id": "l1", "title": "Bills"},
    {"id": "l2", "title": "Home"},
    {"id": "l3", "title": "home"},
    {"title": "No id"},
]


def _client(lists: list[dict[str, Any]] | None = None, **methods: Any) -> MagicMock:
    client = MagicMock()
    client.list_task_lists = AsyncMock(return_value={"items": _LISTS if lists is None else lists})
    for name, value in methods.items():
        setattr(client, name, value)
    return client


@pytest.mark.parametrize(
    ("given", "named"),
    [(None, False), ("", False), ("@default", False), ("l1", True), ("Bills", True)],
)
def test_anything_but_nothing_and_the_alias_names_a_list(given: str | None, named: bool) -> None:
    assert scope.names_a_list(given) is named
    assert scope.UNNAMED_LIST == "@default"


class TestTheListNamed:
    async def test_by_its_id(self) -> None:
        assert await scope.named_task_list(_client(), "l1") == {"id": "l1", "title": "Bills"}

    async def test_by_its_exact_name_before_any_looser_reading(self) -> None:
        """« Home » and « home » both exist: each is itself, neither is ambiguous."""
        assert (await scope.named_task_list(_client(), "Home"))["id"] == "l2"
        assert (await scope.named_task_list(_client(), "home"))["id"] == "l3"

    async def test_by_its_name_whatever_the_case_and_the_outer_spaces(self) -> None:
        assert (await scope.named_task_list(_client(), "  bILLs "))["id"] == "l1"

    async def test_an_id_wins_over_another_list_s_name(self) -> None:
        lists = [{"id": "a", "title": "b"}, {"id": "b", "title": "Other"}]

        assert (await scope.named_task_list(_client(lists), "b"))["id"] == "b"

    async def test_a_name_several_lists_answer_to_is_refused(self) -> None:
        with pytest.raises(ToolValidationError) as refused:
            await scope.named_task_list(_client(), "HOME")

        assert str(refused.value) == scope.AMBIGUOUS_LIST
        assert refused.value.field == scope.LIST_PARAMETER

    @pytest.mark.parametrize("given", ["Wrok", "l9", "No id"])
    async def test_what_no_list_answers_to_is_refused_never_replaced(self, given: str) -> None:
        """Measured 2026-11-10: a list's own id became the provider's default list."""
        with pytest.raises(ToolValidationError) as refused:
            await scope.named_task_list(_client(), given)

        assert str(refused.value) == scope.UNKNOWN_LIST
        assert refused.value.field == scope.LIST_PARAMETER

    @pytest.mark.parametrize("message", [scope.UNKNOWN_LIST, scope.AMBIGUOUS_LIST])
    def test_a_refusal_tells_the_model_how_to_correct_its_call(self, message: str) -> None:
        """The words are the model's (ADR-256): the tool that lists, no value echoed."""
        assert "list_task_lists_tool" in message
        assert "{" not in message and "%" not in message

    async def test_the_account_s_lists_are_read_under_one_published_bound(self) -> None:
        client = _client()

        await scope.named_task_list(client, "l1")

        client.list_task_lists.assert_awaited_once_with(max_results=TASK_LIST_NAMES_SCAN_MAX)

    async def test_an_account_without_a_list_answers_to_nothing(self) -> None:
        client = _client()
        client.list_task_lists = AsyncMock(return_value={"items": None})

        with pytest.raises(ToolValidationError):
            await scope.named_task_list(client, "Bills")


def _preference(connector: ConnectorType | None, preferred: Any = "l2") -> Any:
    """The settings' default list: the active connector, then what its preference names."""
    resolved = (
        AsyncMock(side_effect=preferred)
        if isinstance(preferred, Exception)
        else AsyncMock(return_value=preferred)
    )
    return (
        patch.object(scope, "resolve_active_connector", AsyncMock(return_value=connector)),
        patch.object(scope, "resolve_owner_task_list_id", resolved),
    )


class TestTheDefaultList:
    async def test_it_is_the_one_the_settings_name(self) -> None:
        client = _client()
        active, preferred = _preference(ConnectorType.GOOGLE_TASKS)

        with active, preferred as resolved:
            assert await scope.default_task_list_id(client, USER) == "l2"

        resolved.assert_awaited_once_with(
            client=client, owner_id=USER, connector_type=ConnectorType.GOOGLE_TASKS
        )

    async def test_without_an_active_connector_it_is_the_provider_s(self) -> None:
        active, preferred = _preference(None)

        with active, preferred as resolved:
            assert await scope.default_task_list_id(_client(), USER) == scope.UNNAMED_LIST

        resolved.assert_not_awaited()

    async def test_a_preference_that_cannot_be_read_falls_to_the_provider_s(self) -> None:
        active, preferred = _preference(ConnectorType.MICROSOFT_TASKS, RuntimeError("down"))

        with active, preferred:
            assert await scope.default_task_list_id(_client(), USER) == scope.UNNAMED_LIST


def _default(list_id: str = "l2") -> Any:
    return patch.object(scope, "default_task_list_id", AsyncMock(return_value=list_id))


class TestWhereANewTaskGoes:
    @pytest.mark.parametrize("given", [None, "", "@default"])
    async def test_in_the_default_list_when_nobody_names_one(self, given: str | None) -> None:
        client = _client(get_task_list=AsyncMock(return_value={"id": "l2", "title": "Home"}))

        with _default() as resolved:
            target = await scope.new_task_list(client, USER, given)

        assert target == {"id": "l2", "title": "Home"}
        resolved.assert_awaited_once_with(client, USER)
        client.get_task_list.assert_awaited_once_with("l2")

    async def test_the_provider_s_alias_becomes_the_real_list(self) -> None:
        """The card names the list, and a later act finds the task where it went."""
        client = _client(get_task_list=AsyncMock(return_value={"id": "real", "title": "My Tasks"}))

        with _default(scope.UNNAMED_LIST):
            assert await scope.new_task_list(client, USER, None) == {
                "id": "real",
                "title": "My Tasks",
            }

    async def test_a_default_list_whose_name_cannot_be_read_still_takes_the_task(self) -> None:
        client = _client(get_task_list=AsyncMock(side_effect=RuntimeError("down")))

        with _default():
            assert await scope.new_task_list(client, USER, None) == {"id": "l2", "title": None}

    async def test_in_the_list_named_and_the_default_is_never_asked(self) -> None:
        client = _client(get_task_list=AsyncMock())

        with _default() as resolved:
            target = await scope.new_task_list(client, USER, "bills")

        assert target == {"id": "l1", "title": "Bills"}
        resolved.assert_not_awaited()
        client.get_task_list.assert_not_awaited()

    async def test_a_list_nobody_has_is_refused_never_the_default_one(self) -> None:
        client = _client(get_task_list=AsyncMock())

        with _default() as resolved, pytest.raises(ToolValidationError):
            await scope.new_task_list(client, USER, "Work")

        resolved.assert_not_awaited()


def _looked_up(items: list[dict[str, Any]]) -> Any:
    return patch.object(scope, "last_lookup_items", AsyncMock(return_value=items))


class TestWhatTheConversationLookedUp:
    async def test_without_a_runtime_nothing_is_known(self) -> None:
        with _looked_up([{"id": "t1", FIELD_TASK_LIST_ID: "l2"}]) as read:
            assert await scope.looked_up_task_list_ids(None, "proof") == {}

        read.assert_not_awaited()

    async def test_a_runtime_without_a_store_knows_nothing(self) -> None:
        with _looked_up([{"id": "t1", FIELD_TASK_LIST_ID: "l2"}]):
            assert await scope.looked_up_task_list_ids(make_tool_runtime(), "proof") == {}

    async def test_each_task_keeps_the_list_it_was_first_read_in(self) -> None:
        items = [
            {"id": "t1", FIELD_TASK_LIST_ID: "l2"},
            {"task_id": "t2", FIELD_TASK_LIST_ID: "l3"},
            {"id": "t3"},
            {"id": "t4", FIELD_TASK_LIST_ID: ""},
            {"id": "t1", FIELD_TASK_LIST_ID: "l9"},
            {FIELD_TASK_LIST_ID: "l1"},
        ]
        runtime = make_tool_runtime(store=InMemoryStore())

        with _looked_up(items) as read:
            known = await scope.looked_up_task_list_ids(runtime, "proof")

        assert known == {"t1": "l2", "t2": "l3"}
        assert read.await_args.args[1] == CONTEXT_DOMAIN_TASKS

    async def test_the_real_read_tool_leaves_what_the_next_tool_finds(self) -> None:
        """The real decorator and the lookup agree: the list survives the context store."""
        context = make_runtime_context()
        runtime = make_tool_runtime(context=context, store=InMemoryStore())
        item = RegistryItem(
            id="task_proof",
            type=RegistryItemType.TASK,
            payload={"id": "proof", "title": "Pay", FIELD_TASK_LIST_ID: "other-list"},
            meta=RegistryItemMeta(source="google_tasks", domain=CONTEXT_DOMAIN_TASKS),
        )
        output = UnifiedToolOutput.data_success(message="1 task", registry_updates={item.id: item})
        tool: object = get_tasks_tool
        assert isinstance(tool, StructuredTool) and tool.coroutine is not None

        with (
            installed_runtime_context(context),
            patch(
                "src.domains.agents.tools.tasks_tools._list_tasks_tool_instance.execute",
                AsyncMock(return_value=output),
            ),
        ):
            await tool.coroutine(runtime=runtime)
            known = await scope.looked_up_task_list_ids(runtime, "proof")

        assert known == {"proof": "other-list"}


def _not_here(status: int = 404) -> ConnectorAPIError:
    return ConnectorAPIError(connector_type="google_tasks", status_code=status, detail="no")


def _holding(held: dict[str, Any]) -> MagicMock:
    """An account (l1, l2, l3) whose lists hold these task ids, or answer with a failure."""

    async def get(list_id: str, task_id: str) -> dict[str, Any]:
        answer = held.get(list_id, set())
        if isinstance(answer, Exception):
            raise answer
        if task_id not in answer:
            raise _not_here()
        return {"id": task_id}

    return _client(get_task=AsyncMock(side_effect=get))


class TestATaskNobodySaidTheListOf:
    """Every list is asked: the default list is where a task is MADE, not where it is assumed."""

    @staticmethod
    def _asked(client: MagicMock) -> list[tuple[str, str]]:
        return [asked.args for asked in client.get_task.await_args_list]

    async def test_it_is_found_in_the_list_that_holds_it(self) -> None:
        client = _holding({"l3": {"t"}})

        with _default("l1"):
            assert await scope.find_task_lists(client, USER, ["t"]) == {"t": "l3"}

        client.list_task_lists.assert_awaited_once_with(max_results=TASK_LIST_NAMES_SCAN_MAX)

    async def test_the_default_list_is_asked_first_and_the_asking_stops_once_found(self) -> None:
        """A task made with no list named went there: one call in the common case."""
        client = _holding({"l2": {"t"}})

        with _default("l2"):
            assert await scope.find_task_lists(client, USER, ["t"]) == {"t": "l2"}

        assert self._asked(client) == [("l2", "t")]

    async def test_the_other_lists_follow_in_the_provider_s_order(self) -> None:
        client = _holding({"l3": {"t"}})

        with _default("l2"):
            await scope.find_task_lists(client, USER, ["t"])

        assert self._asked(client) == [("l2", "t"), ("l1", "t"), ("l3", "t")]

    @pytest.mark.parametrize(
        "not_here",
        [
            _not_here(404),
            # Measured on Graph (2026-11-10): the id of ANOTHER list's task is a 400 there.
            _not_here(400),
            ResourceNotFoundError(resource_type="task"),
        ],
    )
    async def test_each_way_a_provider_says_not_here_moves_on_to_the_next_list(
        self, not_here: Exception
    ) -> None:
        client = _holding({"l1": not_here, "l2": {"t"}})

        with _default("l1"):
            assert await scope.find_task_lists(client, USER, ["t"]) == {"t": "l2"}

    @pytest.mark.parametrize(
        "not_here",
        [_not_here(404), _not_here(400), ResourceNotFoundError(resource_type="task")],
    )
    async def test_not_here_from_every_list_is_no_list_holding_it_never_a_failure(
        self, not_here: Exception
    ) -> None:
        """A list that answered « not here » WAS asked: the task is nowhere, said as such."""
        client = _holding({"l1": not_here, "l2": not_here, "l3": not_here})

        with _default("l1"):
            assert await scope.find_task_lists(client, USER, ["t"]) == {}

        assert len(client.get_task.await_args_list) == 3, "every list was asked"

    async def test_tasks_of_several_lists_are_each_found_where_they_live(self) -> None:
        client = _holding({"l1": {"a"}, "l3": {"b"}})

        with _default("l1"):
            found = await scope.find_task_lists(client, USER, ["a", "b", "gone"])

        assert found == {"a": "l1", "b": "l3"}
        assert ("l2", "a") not in self._asked(client), "a task found is asked of no other list"

    @pytest.mark.parametrize("failure", [_not_here(403), _not_here(503), TimeoutError()])
    async def test_a_list_that_could_not_be_asked_is_never_read_as_not_holding_it(
        self, failure: Exception
    ) -> None:
        """« No list holds it » is never told on a list nobody could look in (ADR-303)."""
        client = _holding({"l1": failure})

        with _default("l1"), pytest.raises(type(failure)):
            await scope.find_task_lists(client, USER, ["t"])

    async def test_a_list_that_could_not_be_asked_does_not_hide_a_task_found_elsewhere(
        self,
    ) -> None:
        client = _holding({"l1": TimeoutError(), "l3": {"t"}})

        with _default("l1"):
            assert await scope.find_task_lists(client, USER, ["t"]) == {"t": "l3"}

    async def test_a_defect_is_not_a_list_that_does_not_hold_it(self) -> None:
        client = _holding({"l1": KeyError("bug")})

        with _default("l1"), pytest.raises(KeyError):
            await scope.find_task_lists(client, USER, ["t"])


class TestTheListOfATaskThatExists:
    def _known(self, lists: dict[str, str]) -> Any:
        return patch.object(scope, "looked_up_task_list_ids", AsyncMock(return_value=lists))

    async def test_the_list_named_serves_every_task_and_nothing_else_is_read(self) -> None:
        with self._known({"t1": "l2"}) as known, _default() as default:
            lists = await scope.task_list_ids_of(
                _client(), USER, ["t1", "t2"], "Bills", runtime=None, tool_name="proof"
            )

        assert lists == {"t1": "l1", "t2": "l1"}
        known.assert_not_awaited()
        default.assert_not_awaited()

    async def test_each_task_is_found_where_the_conversation_read_it(self) -> None:
        """The tasks of one answer span several lists: each is acted on in its own."""
        with self._known({"t1": "l2", "t2": "l3"}), _default("l1") as default:
            lists = await scope.task_list_ids_of(
                _client(), USER, ["t1", "t2"], None, runtime=None, tool_name="proof"
            )

        assert lists == {"t1": "l2", "t2": "l3"}
        default.assert_not_awaited()

    async def test_a_task_nobody_read_is_looked_for_in_every_list(self) -> None:
        client = _holding({"l3": {"t9"}})

        with self._known({"t1": "l2"}), _default("l1"):
            lists = await scope.task_list_ids_of(
                client, USER, ["t1", "t9"], "@default", runtime=None, tool_name="proof"
            )

        assert lists == {"t1": "l2", "t9": "l3"}, "found where it lives, not in the default list"
        assert all(
            asked.args[1] == "t9" for asked in client.get_task.await_args_list
        ), "a task the conversation read is not searched again"

    async def test_a_task_no_list_holds_is_left_out_for_its_caller_to_say(self) -> None:
        with self._known({"t1": "l2"}), _default("l1"):
            lists = await scope.task_list_ids_of(
                _holding({}), USER, ["t1", "gone"], None, runtime=None, tool_name="proof"
            )

        assert lists == {"t1": "l2"}

    async def test_one_task_no_list_holds_is_refused_never_acted_on_in_a_list_picked(self) -> None:
        """Before 2026-11-10 it was looked for in the default list, and acted on there."""
        with self._known({}), _default("l1"), pytest.raises(ToolValidationError) as refused:
            await scope.own_task_list_id(
                _holding({}), USER, "gone", {"task_id": "gone"}, runtime=None, tool_name="proof"
            )

        assert str(refused.value) == scope.UNKNOWN_TASK
        assert refused.value.field == "task_id"
        assert "get_tasks_tool" in scope.UNKNOWN_TASK and "{" not in scope.UNKNOWN_TASK

    async def test_a_list_nobody_has_is_refused(self) -> None:
        with self._known({"t1": "l2"}), _default(), pytest.raises(ToolValidationError):
            await scope.task_list_ids_of(
                _client(), USER, ["t1"], "Work", runtime=None, tool_name="proof"
            )

    async def test_a_tool_hands_its_own_runtime_never_one_of_its_arguments(self) -> None:
        """``execute_api_call`` receives no ``runtime``: read there, nothing was ever known."""
        runtime = make_tool_runtime(store=InMemoryStore())

        with self._known({"t1": "l2"}) as known, _default("l1"):
            list_id = await scope.own_task_list_id(
                _client(), USER, "t1", {"task_id": "t1"}, runtime=runtime, tool_name="proof"
            )

        assert list_id == "l2"
        known.assert_awaited_once_with(runtime, "proof")

    async def test_a_tool_s_named_list_is_read_from_its_arguments(self) -> None:
        with self._known({"t1": "l2"}), _default():
            list_id = await scope.own_task_list_id(
                _client(),
                USER,
                "t1",
                {"task_id": "t1", scope.LIST_PARAMETER: "home"},
                runtime=None,
                tool_name="proof",
            )

        assert list_id == "l3"
