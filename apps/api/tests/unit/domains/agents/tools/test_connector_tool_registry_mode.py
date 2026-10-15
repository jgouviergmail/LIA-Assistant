"""A connector tool answers in registry mode, so every reader can read its verdict (ADR-347).

A connector tool in legacy mode (``registry_enabled`` false) answers with a JSON
STRING — its successes, and its failures too: ``handle_error`` returns
``output.model_dump_json()`` there. The readers of the verdict cannot read a
string (``core.tool_outcome.explicit_success`` reads ``success`` on an object or
a dict): the effect register settles the act SUCCEEDED, the tool metrics count
a success, and the ReAct loop loses the structural failure marker. The
pipeline executor alone parsed the JSON back. Found by the cold review of
ADR-347: ``complete_task_tool``, a registered ``reversible`` tool, ran on the
one legacy class still reached through ``execute``.

So every connector tool class of ``src`` runs in registry mode. The one class
kept in legacy mode is never run through ``execute``: the label delete draft's
executor calls its ``execute_api_call`` and reads the payload itself.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain.tools import ToolRuntime

import src.domains.agents.tools  # noqa: F401 - imports every tool module
from src.core.tool_outcome import explicit_success
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.effects.outcome import read_outcome
from src.domains.agents.tools.base import APIKeyConnectorTool, ConnectorTool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.tasks_tools import CompleteTaskTool
from src.domains.connectors.models import ConnectorType
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

#: The connector tool classes kept in legacy mode, each with the reason it is safe.
LEGACY_MODE_CLASSES: dict[str, str] = {
    "DeleteLabelDirectTool": (
        "Never run through execute: the label delete draft's executor calls its "
        "execute_api_call and reads the payload itself."
    ),
}


def _runtime() -> ToolRuntime[LiaRuntimeContext, Any]:
    store = MagicMock()
    store.aget = AsyncMock(return_value=None)
    store.aput = AsyncMock()
    return make_tool_runtime(
        user_id=uuid4(),
        thread_id="t",
        conversation_id="t",
        state={},
        store=store,
        tool_call_id="call",
    )


def _deps() -> MagicMock:
    service = MagicMock()
    service.get_connector_credentials = AsyncMock(return_value={"access_token": "x"})
    deps = MagicMock()
    deps.get_connector_service = AsyncMock(return_value=service)

    async def _run_factory(
        cls: type, cache_key: object, factory: Callable[[], Awaitable[object]]
    ) -> object:
        return MagicMock()

    deps.get_or_create_client = AsyncMock(side_effect=_run_factory)
    deps.db = MagicMock()
    return deps


async def _complete(api_call: AsyncMock) -> object:
    """Run the tool through its real ``execute``; the provider resolution is not the subject."""
    resolved = AsyncMock(return_value=(ConnectorType.GOOGLE_TASKS, None))
    with (
        patch("src.domains.agents.tools.base.get_dependencies", return_value=_deps()),
        patch.object(CompleteTaskTool, "_resolve_category_provider", resolved),
        patch.object(CompleteTaskTool, "execute_api_call", api_call),
    ):
        return await CompleteTaskTool().execute(_runtime(), task_id="task_1")


class TestTheTaskCompletionVerdict:
    async def test_a_refused_completion_reads_as_a_failure_to_every_reader(self) -> None:
        output = await _complete(AsyncMock(side_effect=RuntimeError("provider refused")))

        assert isinstance(output, UnifiedToolOutput)
        assert explicit_success(output) is False
        assert read_outcome(output).succeeded is False

    async def test_a_completion_is_an_action_said_in_the_payload_s_words(self) -> None:
        payload = {
            "success": True,
            "task_id": "task_1",
            "title": "Pay the rent",
            "message": "Task 'Pay the rent' marked as completed",
        }

        output = await _complete(AsyncMock(return_value=payload))

        assert isinstance(output, UnifiedToolOutput)
        assert output.success is True
        assert output.message == payload["message"]
        assert output.structured_data["task_id"] == "task_1"
        assert read_outcome(output).succeeded is True


def _connector_classes() -> Iterator[type]:
    """Every concrete connector tool class defined in ``src`` (test doubles excluded)."""
    seen: set[type] = set()
    pending: list[type] = [ConnectorTool, APIKeyConnectorTool]
    while pending:
        for subclass in pending.pop().__subclasses__():
            if subclass in seen:
                continue
            seen.add(subclass)
            pending.append(subclass)
            if subclass.__module__.startswith("src.") and not inspect.isabstract(subclass):
                yield subclass


class TestEveryConnectorToolRunsInRegistryMode:
    def test_the_census_sees_the_catalogue(self) -> None:
        names = {cls.__name__ for cls in _connector_classes()}

        assert {"CompleteTaskTool", "DeleteLabelDirectTool"} <= names
        assert len(names) > 40

    def test_only_the_declared_classes_run_in_legacy_mode(self) -> None:
        legacy = sorted(cls.__name__ for cls in _connector_classes() if not cls.registry_enabled)

        assert legacy == sorted(LEGACY_MODE_CLASSES), (
            "A connector tool in legacy mode answers with a JSON string, which no "
            "reader of the verdict can read: set registry_enabled = True and return "
            f"a UnifiedToolOutput from format_registry_response. Legacy: {legacy}"
        )
