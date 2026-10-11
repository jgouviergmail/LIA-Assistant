"""Opaque task delegates are not independent reads or authorized recovery actions."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Annotated, Literal
from uuid import uuid4

import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import InjectedToolArg, StructuredTool

from src.domains.agents.analysis.requested_outcomes import GoalRequirement
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.react_observed_gaps import observed_gaps, requested_coverage
from src.domains.agents.nodes.react_recovery import should_recover
from src.domains.agents.registry.catalogue import ParameterSchema, ToolManifest, is_read_only_tool
from src.domains.agents.semantic.value_bindings import binding_scope_from_config
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.tool_registry import register_external_tool
from src.infrastructure.mcp.registration import build_mcp_react_task_manifest
from tests.unit.domains.agents.nodes.react_execution_harness import execution_graph, state_result
from tests.unit.domains.agents.nodes.test_react_checkpointed_execution import (
    Calls,
    _call,
    _contacts,
    _context,
    _register,
    _requested_state,
    _state,
    contracts,
    no_services,
)

pytestmark = pytest.mark.unit
_FIXTURES = (contracts, no_services)
ProxyOutcome = Literal["failed", "partial", "success"]


@dataclass
class Delegation:
    outcome: ProxyOutcome
    calls: list[str] = field(default_factory=list)
    active: int = 0
    maximum: int = 0
    cutoffs: list[str] = field(default_factory=list)

    async def invoke(
        self,
        query: str = "Ada",
        runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
    ) -> UnifiedToolOutput:
        assert runtime is not None
        bindings, _account, sources = binding_scope_from_config(runtime.config)
        assert not bindings and not sources, "old semantic proof must not enter the delegate"
        cutoff = runtime.config["configurable"]["semantic_source_valid_after"]
        assert isinstance(cutoff, str)
        self.cutoffs.append(cutoff)
        self.calls.append(query)
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        try:
            await asyncio.sleep(0.01)
            return self.result(query)
        finally:
            self.active -= 1

    def result(self, query: str) -> UnifiedToolOutput:
        if self.outcome == "failed":
            return UnifiedToolOutput.failure("opaque task failed", error_code="INTERNAL_ERROR")
        result = _contacts(query)
        if self.outcome == "partial":
            result.metadata["partial"] = True
        return result


def _proxy(coroutine: Callable[..., Awaitable[UnifiedToolOutput]]) -> ToolManifest:
    name = f"mcp_opaque_fixture_{uuid4().hex}_task"
    register_external_tool(
        StructuredTool.from_function(
            coroutine=coroutine, name=name, description="isolated delegate boundary"
        )
    )
    manifest = build_mcp_react_task_manifest(
        tool_name=name,
        agent_name="contact_agent",
        server_name="Fixture",
        description="Opaque task fixture",
        parameters=[
            ParameterSchema(
                name="query", type="string", required=False, description="fixture input"
            )
        ],
        semantic_keywords=[],
    )
    assert manifest.delegates_execution
    assert is_read_only_tool(manifest), "global classification remains unchanged"
    # Even an accidental opt-in must not turn opaque execution into a cached parallel read.
    return replace(manifest, concurrency_safe=True, result_reuse_ttl_seconds=60)


def _assert_invalidated(state: MessagesState, delegate: Delegation) -> None:
    assert state["react_read_results"] == {}
    assert state["semantic_value_bindings"] == []
    assert state["semantic_source_observations"] == {}
    assert state["semantic_source_valid_after"] == delegate.cutoffs[-1]
    assert not observed_gaps(state), "an opaque task outcome is not a started read obligation"
    assert len(state["registry"]) >= 1, "canonical successful data remains available"


@pytest.mark.parametrize("outcome", ["failed", "partial", "success"])
async def test_actual_proxy_factory_cannot_opt_into_read_reuse_or_concurrency(
    contracts: list[ToolManifest],
    outcome: ProxyOutcome,
) -> None:
    monitor, delegate = Calls(), Delegation(outcome)
    read = _register(monitor.read)
    monitor.tool_name = read.name
    proxy = _proxy(delegate.invoke)
    contracts.extend([read, proxy])
    state = _state(_call(read, "read"), _call(proxy, "p1"), _call(proxy, "p2"))
    result = state_result(await execution_graph().ainvoke(state, context=_context()))
    assert delegate.calls == ["Ada", "Ada"]
    assert delegate.maximum == 1
    assert len(result["react_read_observations"]) == 1, "only the actual native read is booked"
    _assert_invalidated(result, delegate)
    result["messages"].append(AIMessage("", id="fresh-read", tool_calls=[_call(read, "r2")]))
    await execution_graph().ainvoke(result, context=_context())
    assert monitor.seen == ["Ada", "Ada"], "delegation invalidates the prior exact read cache"


async def _failed_read(query: str = "Ada") -> UnifiedToolOutput:
    return UnifiedToolOutput.failure("actual native read unavailable", error_code="INTERNAL_ERROR")


@pytest.mark.parametrize("outcome", ["failed", "partial"])
@pytest.mark.parametrize("kind", ["read", "action"])
async def test_proxy_does_not_replay_during_recovery_for_another_failed_read(
    contracts: list[ToolManifest],
    outcome: ProxyOutcome,
    kind: Literal["read", "action"],
) -> None:
    delegate = Delegation(outcome)
    proxy = _proxy(delegate.invoke)
    native = replace(_register(_failed_read), agent="emails_agent")
    contracts.extend([proxy, native])
    goal = GoalRequirement(
        domain="contact", label="opaque result", source_quote="obtiens le résultat Ada", kind=kind
    )
    state = _requested_state(_call(proxy, "p1"), goal)
    state["react_tool_names"].append(native.name)
    state["react_hitl_map"][native.name] = False
    state["messages"] = [
        AIMessage("", id="first", tool_calls=[_call(proxy, "p1"), _call(native, "r1")])
    ]
    state = state_result(await execution_graph().ainvoke(state, context=_context()))
    assert requested_coverage(state)[0].status == "unknown"
    assert len(state["react_read_observations"]) == 1
    state["messages"].append(AIMessage("Native lookup unavailable.", id="draft"))
    assert should_recover(state)
    cutoff = state["semantic_source_valid_after"]
    state["react_recovery_passes"] = [
        {
            "anchor_id": "draft",
            "draft": "Native lookup unavailable.",
            "unresolved": ["email lookup"],
        }
    ]
    state["messages"].append(AIMessage("", id="recovery", tool_calls=[_call(proxy, "p2")]))
    result = state_result(await execution_graph().ainvoke(state, context=_context()))
    _assert_no_delegation_replay(result, delegate, cutoff)


def _assert_no_delegation_replay(
    state: MessagesState, delegate: Delegation, cutoff: str | None
) -> None:
    assert delegate.calls == ["Ada"]
    assert state["semantic_source_valid_after"] == cutoff
    assert requested_coverage(state)[0].status == "unknown"
    assert len(state["react_read_observations"]) == 1
    answer = next(
        message
        for message in state["messages"]
        if isinstance(message, ToolMessage) and message.tool_call_id == "p2"
    )
    assert answer.artifact is not None
    assert "not executed" in str(answer.content)
