"""A routine's pre-approved server runs its ``confirm`` tools; any other is refused (spec D9).

A routine runs with nobody to ask, so the gate refuses its ``confirm`` calls. The
run of a routine whose form ticked a server publishes that pre-approval: the gate
then runs a ``confirm`` call of THAT server under an approved scope the register
names ``routine_preapproval``, with the routine as its reference — never the
person's ``tool_confirmation``, which they did not give for this call. A server
not ticked is refused and named, exactly as before. ReAct reads the same
predicate before it would refuse in the loop.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from src.core.context import UserMCPToolsContext, request_tool_manifests_ctx, user_mcp_tools_ctx
from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.gate import ERROR_CONFIRMATION_IMPOSSIBLE
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.shared.mcp_preapproval import (
    ROUTINE_PREAPPROVAL_KIND,
    MCPPreapproval,
    mcp_preapproval_scope,
)
from src.infrastructure.mcp.user_context import _build_user_tool_manifest
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from tests.helpers.mcp_access import installed_shared_mcp_access

pytestmark = [pytest.mark.unit]

_SCHEMA: dict[str, Any] = {"type": "object", "properties": {"note_id": {"type": "string"}}}
_ROUTINE = "4f1c9e2a-0000-4000-8000-00000000aaaa"
REACHED: list[dict[str, Any]] = []


@pytest.fixture(autouse=True)
def _routine_run() -> Iterator[None]:
    """A routine's turn: an automated source nobody watches."""
    REACHED.clear()
    gate_runtime.reset_policy_cache()
    sink = AsyncMock()
    with (
        installed_shared_mcp_access() as actor,
        patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=SimpleNamespace(
                user_id=actor.id,
                thread_id="thread-routine",
                execution_mode="pipeline",
                is_automated_source=True,
            ),
        ),
        patch("src.domains.agents.effects.runtime.record_integrity_event", sink),
        patch("src.domains.agents.effects.treatments.record_integrity_event", sink),
        treatment_collector(run_id="routine-run"),
    ):
        yield
    gate_runtime.reset_policy_cache()


async def _server(self: UserMCPToolAdapter, **kwargs: Any) -> UnifiedToolOutput:
    REACHED.append(dict(kwargs))
    return UnifiedToolOutput.action_success(message="done")


def _destructive_tool(server_id: uuid.UUID) -> tuple[UserMCPToolAdapter, ToolManifest]:
    adapter = UserMCPToolAdapter.from_discovered_tool(
        server_id=server_id,
        user_id=uuid.uuid4(),
        server_name="notes",
        tool_name="delete_note",
        description="Delete a note",
        input_schema=_SCHEMA,
        server_prefix="abcd1234",
    )
    manifest = _build_user_tool_manifest(
        adapter_name=adapter.name,
        tool_name=adapter.mcp_tool_name,
        description="Delete a note",
        input_schema=_SCHEMA,
        server_name="notes",
        server_domain="mcp_notes",
        hitl_required=False,
        annotations={"destructive_hint": True},
        server_key=str(server_id),
    )
    return adapter, manifest


@contextmanager
def _offered(adapter: UserMCPToolAdapter, manifest: ToolManifest) -> Iterator[None]:
    ctx = UserMCPToolsContext(tool_manifests=[manifest], tool_instances={adapter.name: adapter})
    token = user_mcp_tools_ctx.set(ctx)
    offered = request_tool_manifests_ctx.set([manifest])
    try:
        yield
    finally:
        request_tool_manifests_ctx.reset(offered)
        user_mcp_tools_ctx.reset(token)


class _Ledger:
    def __init__(self) -> None:
        self.claims: list[Any] = []
        self.refusals: list[tuple[str, str]] = []
        self.refused: list[Any] = []

    async def claim(self, request: Any) -> Any:
        self.claims.append(request)
        return gate_runtime.ClaimTicket(
            effect_id=uuid.uuid4(), claim_token=uuid.uuid4(), served_result=None
        )

    async def close(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def abandon(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def refuse(self, request: Any, *, error_code: str) -> None:
        self.refusals.append((request.tool_name, error_code))
        self.refused.append(request)


def _routine_step() -> EffectScope:
    """What the executor publishes around a routine's step: nobody approved it."""
    return EffectScope(
        run_id="routine-run", idempotency_key="routine-run:step:s1", source="scheduled"
    )


class TestWhatAPreapprovalNeverCovers:
    """A pre-approval names MCP SERVERS: nothing else is ever confirmed by it."""

    def test_a_tool_of_no_mcp_server_is_never_preapproved(self) -> None:
        from src.domains.agents.effects.preapproval import is_preapproved

        server_id = uuid.uuid4()
        adapter, manifest = _destructive_tool(server_id)
        native = replace(manifest, mcp_origin=None)
        ticked = MCPPreapproval(servers=frozenset({str(server_id)}), routine_id=_ROUTINE)

        with _offered(adapter, native), mcp_preapproval_scope(ticked):
            assert is_preapproved(adapter.name) is False

    def test_a_name_resolving_only_through_a_suffix_is_never_preapproved(self) -> None:
        """The tool's OWN declaration decides; a stripped suffix names another tool."""
        from src.domains.agents.effects.preapproval import is_preapproved

        server_id = uuid.uuid4()
        adapter, manifest = _destructive_tool(server_id)
        ticked = MCPPreapproval(servers=frozenset({str(server_id)}), routine_id=_ROUTINE)

        with _offered(adapter, manifest), mcp_preapproval_scope(ticked):
            assert is_preapproved(adapter.name) is True
            assert is_preapproved(f"{adapter.name}_tool") is False


class TestThePipelineGate:
    async def test_preapproved_server_runs_its_confirm_tool_in_a_routine(self) -> None:
        server_id = uuid.uuid4()
        adapter, manifest = _destructive_tool(server_id)
        ledger = _Ledger()
        preapproval = MCPPreapproval(servers=frozenset({str(server_id)}), routine_id=_ROUTINE)
        with (
            _offered(adapter, manifest),
            patch.object(UserMCPToolAdapter, "_call_server", new=_server),
            patch.object(gate_runtime, "_LEDGER", ledger),
            mcp_preapproval_scope(preapproval),
            effect_scope(_routine_step()),
        ):
            await adapter.coroutine(note_id="n-1")

        assert REACHED == [{"note_id": "n-1"}], "the pre-approved act ran"
        (claim,) = ledger.claims
        assert (claim.approval_kind, claim.approval_ref) == (ROUTINE_PREAPPROVAL_KIND, _ROUTINE)
        assert ledger.refusals == []

    async def test_unlisted_server_is_still_refused_and_named(self) -> None:
        server_id = uuid.uuid4()
        adapter, manifest = _destructive_tool(server_id)
        ledger = _Ledger()
        another = MCPPreapproval(servers=frozenset({str(uuid.uuid4())}), routine_id=_ROUTINE)
        with (
            _offered(adapter, manifest),
            patch.object(UserMCPToolAdapter, "_call_server", new=_server),
            patch.object(gate_runtime, "_LEDGER", ledger),
            mcp_preapproval_scope(another),
            effect_scope(_routine_step()),
        ):
            await adapter.coroutine(note_id="n-1")

        assert REACHED == [], "a server not ticked is never reached unasked"
        assert ledger.claims == []
        assert ledger.refusals == [(adapter.name, ERROR_CONFIRMATION_IMPOSSIBLE)]

    async def test_without_a_routine_nothing_is_preapproved(self) -> None:
        """Outside a routine run no pre-approval exists: the attended gate asks as ever."""
        server_id = uuid.uuid4()
        adapter, manifest = _destructive_tool(server_id)
        ledger = _Ledger()
        with (
            _offered(adapter, manifest),
            patch.object(UserMCPToolAdapter, "_call_server", new=_server),
            patch.object(gate_runtime, "_LEDGER", ledger),
            effect_scope(_routine_step()),
        ):
            await adapter.coroutine(note_id="n-1")

        assert REACHED == [] and ledger.claims == []


_LOOP_CONFIG: RunnableConfig = {
    "configurable": {"thread_id": "thread-routine"},
    "metadata": {"run_id": "routine-run"},
}


class TestTheLoopReadsTheSamePredicate:
    async def test_react_routine_uses_the_same_predicate(self) -> None:
        from src.domains.agents.nodes.react_call_execution import _approve

        server_id = uuid.uuid4()
        adapter, manifest = _destructive_tool(server_id)
        state: Any = {"react_hitl_map": {adapter.name: True}, "user_language": "en"}
        call: Any = {"id": "c1", "name": adapter.name, "args": {"note_id": "n-1"}}
        ports = SimpleNamespace(interrupt=lambda payload: pytest.fail("a routine asks nobody"))
        ticked = MCPPreapproval(servers=frozenset({str(server_id)}), routine_id=_ROUTINE)
        not_ticked = MCPPreapproval(servers=frozenset({"elsewhere"}), routine_id=_ROUTINE)

        with (
            _offered(adapter, manifest),
            patch(
                "src.domains.agents.nodes.react_call_execution.turn_has_nobody_to_ask",
                return_value=True,
            ),
            patch.object(gate_runtime, "_LEDGER", _Ledger()),
        ):
            with mcp_preapproval_scope(ticked):
                proceeds = await _approve(call, state, ports, _LOOP_CONFIG)  # type: ignore[arg-type]
            with mcp_preapproval_scope(not_ticked):
                refused = await _approve(call, state, ports, _LOOP_CONFIG)  # type: ignore[arg-type]

        assert proceeds is None, "the pre-approved call proceeds to the gate"
        assert refused is not None and refused.artifact == "tool_call_not_run", "others refused"

    async def test_a_call_the_loop_refuses_is_in_the_register_like_the_gates(self) -> None:
        """Measured 2026-10-30 on Docker dev: the Pipeline routine's refusal had its row,
        the ReAct routine's none — the loop stops the call BEFORE the gate (D8)."""
        from src.domains.agents.nodes.react_call_execution import _approve

        adapter, manifest = _destructive_tool(uuid.uuid4())
        state: Any = {"react_hitl_map": {adapter.name: True}, "user_language": "en"}
        call: Any = {"id": "c1", "name": adapter.name, "args": {"note_id": "n-1"}}
        ports = SimpleNamespace(interrupt=lambda payload: pytest.fail("a routine asks nobody"))
        ledger = _Ledger()

        with (
            _offered(adapter, manifest),
            patch(
                "src.domains.agents.nodes.react_call_execution.turn_has_nobody_to_ask",
                return_value=True,
            ),
            patch.object(gate_runtime, "_LEDGER", ledger),
        ):
            refused = await _approve(call, state, ports, _LOOP_CONFIG)  # type: ignore[arg-type]

        assert refused is not None and refused.artifact == "tool_call_not_run"
        assert ledger.refusals == [(adapter.name, ERROR_CONFIRMATION_IMPOSSIBLE)]
        (request,) = ledger.refused
        assert (request.run_id, request.idempotency_key) == (
            "routine-run",
            "call:c1",
        ), "filed under the TURN and its call, never the thread"
        assert request.mutation_policy == "confirm"
        assert REACHED == [], "nothing reached the server"

    def test_the_loop_never_files_a_preapproval_as_the_persons_confirmation(self) -> None:
        """The call runs unapproved by a person; the gate files the routine's pre-approval."""
        from src.domains.agents.nodes.react_call_execution import asked_in_the_loop

        server_id = uuid.uuid4()
        adapter, manifest = _destructive_tool(server_id)
        state: Any = {"react_hitl_map": {adapter.name: True}}
        ticked = MCPPreapproval(servers=frozenset({str(server_id)}), routine_id=_ROUTINE)

        with _offered(adapter, manifest):
            assert asked_in_the_loop(adapter.name, state) is True
            with mcp_preapproval_scope(ticked):
                assert asked_in_the_loop(adapter.name, state) is False
