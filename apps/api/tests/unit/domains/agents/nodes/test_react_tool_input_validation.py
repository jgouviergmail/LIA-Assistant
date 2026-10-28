"""The ReAct execution door validates before a tool can produce an effect."""

from __future__ import annotations

from typing import Literal
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.nodes.react_egress_question import invoke_with_settlement
from src.domains.agents.orchestration.parallel_executor import _build_tool_runtime
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.email_self_tools import send_email_to_me_tool
from src.domains.agents.tools.local_query_tool import local_query_engine_tool
from src.domains.agents.tools.mcp_react_tools import _MCPReActWrapper
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper
from src.domains.agents.tools.tasks_tools import get_tasks_tool
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from tests.helpers.mcp_access import installed_shared_mcp_access
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.unit


class _Inputs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int = Field(ge=1)


@pytest.mark.parametrize(
    "args",
    [
        {"count": 1, "body_text_placeholder": "invented"},
        {"count": 1, "force_refresh": True},
        {"count": 0},
        {},
    ],
)
async def test_invalid_arguments_return_a_typed_refusal_without_running(
    args: dict[str, object],
) -> None:
    effects: list[int] = []

    async def mutate(count: int) -> UnifiedToolOutput:
        effects.append(count)
        return UnifiedToolOutput(success=True, message="ran")

    original = StructuredTool.from_function(
        coroutine=mutate, name="mutation", description="test", args_schema=_Inputs
    )
    result = await invoke_with_settlement(
        ReactToolWrapper(original), args, timeout=1, state={}, tool_name=original.name
    )

    assert result.success is False
    assert result.error_code == ToolErrorCode.INVALID_INPUT
    assert "INVALID_INPUT" in result.message
    assert effects == []


@pytest.mark.parametrize(
    ("original", "args", "issue"),
    [
        (send_email_to_me_tool, {"body_text_placeholder": "invented"}, "body_text_placeholder"),
        (get_tasks_tool, {"force_refresh": True}, "force_refresh"),
        (local_query_engine_tool, {"query": "SELECT private data"}, "query"),
    ],
)
async def test_native_tool_schemas_are_enforced(
    original: BaseTool, args: dict[str, object], issue: str
) -> None:
    injected = _build_tool_runtime(original, args, {}, None)
    result = await invoke_with_settlement(
        ReactToolWrapper(original), injected, timeout=1, state={}, tool_name=original.name
    )

    assert result.success is False
    assert result.error_code == ToolErrorCode.INVALID_INPUT
    assert issue in result.message


async def test_mcp_schema_validation_rejects_a_wrong_aliased_parameter_type() -> None:
    original = MCPToolAdapter.from_mcp_tool(
        "test",
        "query",
        "test",
        {"type": "object", "properties": {"_limit": {"type": "integer"}}, "required": ["_limit"]},
    )
    result = await invoke_with_settlement(
        ReactToolWrapper(original), {"_limit": "all"}, timeout=1, state={}, tool_name=original.name
    )

    assert result.success is False
    assert result.error_code == ToolErrorCode.INVALID_INPUT
    assert "_limit" in result.message


@pytest.mark.parametrize("additional", [True, None, False, "patterned"])
@pytest.mark.parametrize("door", ["react", "ainvoke"])
@pytest.mark.parametrize("has_properties", [True, False])
async def test_mcp_extra_arguments_follow_the_server_schema(
    additional: bool | None | Literal["patterned"],
    door: Literal["react", "ainvoke"],
    has_properties: bool,
) -> None:
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"query": {"type": "string"}} if has_properties else {},
        "required": ["query"] if has_properties else [],
    }
    if additional == "patterned":
        schema["additionalProperties"] = False
        schema["patternProperties"] = {"^page$": {"type": "integer"}}
    elif additional is not None:
        schema["additionalProperties"] = additional
    original = MCPToolAdapter.from_mcp_tool("test", "search", "test", schema)
    received: list[dict[str, object]] = []

    async def answer(_server: str, _tool: str, arguments: dict[str, object]) -> str:
        received.append(arguments)
        return '{"answer": "found"}'

    manager = AsyncMock()
    manager.call_tool.side_effect = answer
    with (
        installed_shared_mcp_access() as actor,
        installed_runtime_context(user_id=actor.id),
        # A real turn publishes its consultation register; without one the
        # gate schedules an integrity write the loop teardown cuts short.
        treatment_collector(run_id="mcp-extra-arguments"),
        patch("src.domains.agents.effects.runtime.resolve_policy", return_value="read"),
        patch("src.infrastructure.mcp.client_manager.get_mcp_client_manager", return_value=manager),
    ):
        args = {"query": "fictional", "page": 1} if has_properties else {"page": 1}
        if door == "react":
            result = await invoke_with_settlement(
                ReactToolWrapper(original), args, timeout=1, state={}, tool_name=original.name
            )
            assert result.success is (additional is not False)
            if additional is False:
                assert result.error_code == ToolErrorCode.INVALID_INPUT
        elif additional is False:
            with pytest.raises(ValueError):
                await original.ainvoke(args)
        else:
            result = await original.ainvoke(args)
            assert result.success is True

    expected = [{"query": "fictional", "page": 1}] if has_properties else [{"page": 1}]
    assert received == ([] if additional is False else expected)


@pytest.mark.parametrize("personal", [False, True])
@pytest.mark.parametrize("door", ["react", "ainvoke", "subagent", "generic"])
@pytest.mark.parametrize("missing_wire", [False, True])
async def test_both_mcp_adapters_keep_wire_aliases_converted_values_and_extras(
    personal: bool, door: Literal["react", "ainvoke", "subagent", "generic"], missing_wire: bool
) -> None:
    schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "model_dump": {"type": "string"},
            "page-limit": {"type": "integer"},
            "from": {"type": "string"},
        },
        "required": ["model_dump", "page-limit", "from"],
        "additionalProperties": True,
    }
    received: list[dict[str, object]] = []

    async def shared_answer(_server: str, _tool: str, arguments: dict[str, object]) -> str:
        received.append(arguments)
        return '{"answer": "found"}'

    async def personal_answer(
        *,
        user_id: UUID,
        server_id: UUID,
        tool_name: str,
        arguments: dict[str, object],
        timeout_seconds: int,
    ) -> str:
        received.append(arguments)
        return '{"answer": "found"}'

    provider = AsyncMock()
    provider.call_tool.side_effect = personal_answer if personal else shared_answer
    with (
        installed_shared_mcp_access() as actor,
        installed_runtime_context(user_id=actor.id),
        # The turn's consultation register, published as in the test above.
        treatment_collector(run_id="mcp-wire-aliases"),
        patch("src.domains.agents.effects.runtime.resolve_policy", return_value="read"),
        patch(
            "src.infrastructure.mcp.client_manager.get_mcp_client_manager", return_value=provider
        ),
        patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=provider),
    ):
        original = (
            UserMCPToolAdapter.from_discovered_tool(
                uuid4(), actor.id, "test", "search", "test", schema
            )
            if personal
            else MCPToolAdapter.from_mcp_tool("test", "search", "test", schema)
        )
        args = {
            "model_dump": "fictional",
            "page-limit": "2",
            "from": "current",
            "include_totals": True,
            "mcp_arg_0": "fictional dynamic",
        }
        if missing_wire:
            args.pop("model_dump")
        if door == "react":
            result = await invoke_with_settlement(
                ReactToolWrapper(original), args, timeout=1, state={}, tool_name=original.name
            )
            assert result.success is (not missing_wire)
            if missing_wire:
                assert result.error_code == ToolErrorCode.INVALID_INPUT
                assert "model_dump" in result.message
        elif missing_wire:
            target = (
                original
                if door == "ainvoke"
                else ReactToolWrapper(original) if door == "generic" else _MCPReActWrapper(original)
            )
            with pytest.raises(ValueError):
                await target.ainvoke(args)
        elif door == "ainvoke":
            result = await original.ainvoke(args)
            assert result.success is True
        else:
            wrapper = (
                ReactToolWrapper(original) if door == "generic" else _MCPReActWrapper(original)
            )
            result = await wrapper.ainvoke(args)
            assert "result received" in result

    expected = [
        {
            "model_dump": "fictional",
            "page-limit": 2,
            "from": "current",
            "include_totals": True,
            "mcp_arg_0": "fictional dynamic",
        }
    ]
    assert received == ([] if missing_wire else expected)


async def test_validated_values_and_the_hidden_runtime_reach_the_coroutine() -> None:
    seen: list[tuple[int, ToolRuntime]] = []

    async def read(count: int, runtime: ToolRuntime) -> UnifiedToolOutput:
        seen.append((count, runtime))
        return UnifiedToolOutput(success=True, message="read")

    original = StructuredTool.from_function(coroutine=read, name="read", description="test")
    injected = _build_tool_runtime(original, {"count": "2"}, {}, None)
    result = await invoke_with_settlement(
        ReactToolWrapper(original), injected, timeout=1, state={}, tool_name=original.name
    )

    assert result.success is True
    assert seen == [(2, injected["runtime"])]
    assert isinstance(seen[0][0], int)
    assert seen[0][1] is injected["runtime"]


async def test_an_extra_argument_is_refused_for_an_inferred_schema_too() -> None:
    effects: list[int] = []

    async def mutate(count: int) -> UnifiedToolOutput:
        effects.append(count)
        return UnifiedToolOutput(success=True, message="ran")

    original = StructuredTool.from_function(coroutine=mutate, name="mutate", description="test")
    result = await invoke_with_settlement(
        ReactToolWrapper(original),
        {"count": 1, "force_refresh": True},
        timeout=1,
        state={},
        tool_name=original.name,
    )

    assert result.success is False
    assert result.error_code == ToolErrorCode.INVALID_INPUT
    assert effects == []
