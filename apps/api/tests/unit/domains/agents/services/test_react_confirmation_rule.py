"""ReAct asks before a call on ONE predicate, the gate's own (spec 2026-10-29 D8).

The loop asks the person before a call when its ``react_hitl_map`` says so; the
effect gate refuses a ``confirm`` call nobody approved, turning it into a draft
that ENDS the loop (ADR-298 measured it). Two rules meant the gate refused what
the loop never asked: a standard MCP tool its server declares destructive, with
the server's confirmation off, was bound unasked (the map read the server
setting alone), and an administrator's iterative server was not expanded, so
its destructive tools were reachable only through a task the loop cannot see
inside. ``requires_confirmation`` is the gate's rule, read for every bound tool —
an expanded individual on its OWN manifest.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID

import pytest

from src.core.context import (
    UserMCPToolsContext,
    request_tool_manifests_ctx,
    user_mcp_tools_ctx,
)
from src.domains.agents.effects.gate import GateAction, decide_effect
from src.domains.agents.effects.scope import react_call_scope
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.confirmation_rule import (
    requires_confirmation,
    task_requires_confirmation,
)
from src.domains.agents.registry.reactive_manifests import (
    register_reactive_manifest,
    reset_reactive_manifests,
)
from src.domains.agents.services.react_tool_selector import ReactToolSelector
from src.infrastructure.mcp.registration import (
    _register_iterative_task_tool,
    build_mcp_react_task_manifest,
    build_mcp_tool_manifest,
)
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter

pytestmark = [pytest.mark.unit]

_SERVER_ID = UUID("770baa3e-1111-2222-3333-444455556666")
_ADMIN_KEY = "notes"
_ADMIN_TASK = f"mcp_{_ADMIN_KEY}_task"
_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


def _select(manifests: list[ToolManifest], ctx: UserMCPToolsContext) -> dict[str, bool]:
    manifests_token = request_tool_manifests_ctx.set(manifests)
    ctx_token = user_mcp_tools_ctx.set(ctx)
    try:
        _wrapped, hitl_map = ReactToolSelector().select(intelligence=None)
    finally:
        user_mcp_tools_ctx.reset(ctx_token)
        request_tool_manifests_ctx.reset(manifests_token)
    return hitl_map


class TestTheStandardServers:
    def test_standard_destructive_tool_is_asked_with_confirmation_off(self) -> None:
        destructive = {"destructive_hint": True}
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=_SERVER_ID,
            user_id=UUID(int=1),
            server_name="atars",
            tool_name="delete_signal",
            description="Delete a signal",
            input_schema=_SCHEMA,
            annotations=destructive,
        )
        manifest = build_mcp_tool_manifest(
            adapter.name,
            "mcp_atars_agent",
            adapter.name,
            "Delete a signal",
            _SCHEMA,
            [],
            False,
            annotations=destructive,
            mcp_origin="user",
            mcp_server_key=str(_SERVER_ID),
        )
        ctx = UserMCPToolsContext()
        ctx.tool_instances[adapter.name] = adapter
        ctx.tool_manifests = [manifest]

        assert manifest.mutation_policy == "confirm", "the gate refuses it unasked"
        assert _select([manifest], ctx)[adapter.name] is True


@pytest.fixture
def admin_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., ToolManifest]]:
    """An administrator's iterative server, its individuals out of the catalogue (Task 2)."""
    from src.domains.agents.tools import tool_registry

    monkeypatch.setattr(tool_registry, "_TOOL_REGISTRY", {})
    monkeypatch.setattr(tool_registry, "_INITIALIZED", True)
    reset_reactive_manifests()

    def install(*, app: bool) -> ToolManifest:
        hinted = (
            ("list_notes", {"read_only_hint": True}),
            ("drop_note", {"destructive_hint": True}),
        )
        for rpc, hints in hinted:
            adapter = MCPToolAdapter.from_mcp_tool(
                _ADMIN_KEY, rpc, rpc, _SCHEMA, app_resource_uri="ui://notes" if app else None
            )
            tool_registry.register_external_tool(adapter)
            register_reactive_manifest(
                build_mcp_tool_manifest(
                    adapter.name,
                    f"mcp_{_ADMIN_KEY}_agent",
                    rpc,
                    rpc,
                    _SCHEMA,
                    [],
                    False,
                    annotations=hints,
                    mcp_origin="admin",
                    mcp_server_key=_ADMIN_KEY,
                )
            )
        assert _register_iterative_task_tool(_ADMIN_TASK, _ADMIN_KEY, "Notes")
        return build_mcp_react_task_manifest(
            _ADMIN_TASK,
            f"mcp_{_ADMIN_KEY}_agent",
            _ADMIN_KEY,
            "Notes",
            [],
            [],
            False,
            mcp_origin="admin",
            mcp_server_key=_ADMIN_KEY,
        )

    yield install
    reset_reactive_manifests()


class TestTheAdministratorIterativeServers:
    def test_admin_iterative_server_is_expanded_and_its_destructive_tool_asked(
        self, admin_server: Callable[..., ToolManifest]
    ) -> None:
        hitl_map = _select([admin_server(app=False)], UserMCPToolsContext())

        assert hitl_map[f"mcp_{_ADMIN_KEY}_drop_note"] is True, "asked in the loop"
        assert hitl_map[f"mcp_{_ADMIN_KEY}_list_notes"] is False
        assert _ADMIN_TASK in hitl_map, "the delegation door stays bound"

    def test_mcp_app_server_keeps_its_task_tool(
        self, admin_server: Callable[..., ToolManifest]
    ) -> None:
        hitl_map = _select([admin_server(app=True)], UserMCPToolsContext())

        assert set(hitl_map) == {_ADMIN_TASK}, "an MCP App keeps its task tool and D5"


class TestTheNativeTools:
    def test_native_tools_unchanged(self) -> None:
        """No native declares ``confirm``: the predicate reads their HITL flag as before."""
        from src.domains.agents.registry.agent_registry import AgentRegistry
        from src.domains.agents.registry.catalogue_loader import initialize_catalogue

        registry = AgentRegistry()
        initialize_catalogue(registry)
        natives = registry.list_tool_manifests()

        assert natives, "the catalogue is loaded"
        changed = [
            m.name
            for m in natives
            if requires_confirmation(m) != bool(m.permissions and m.permissions.hitl_required)
        ]
        assert changed == []


class TestAnAskedCallIsAskedOnce:
    def test_an_asked_call_is_ledgered_once_and_not_asked_twice(self) -> None:
        """Asked in the loop, the call runs under its approval: claimed, never a new draft."""
        config: dict[str, Any] = {"configurable": {"thread_id": "t"}, "metadata": {"run_id": "r"}}

        asked = react_call_scope(config, "call-1", approved=True)
        unasked = react_call_scope(config, "call-2", approved=False)

        assert asked.approved is True
        assert decide_effect("confirm", asked).action is GateAction.LEDGER
        assert decide_effect("confirm", unasked).action is GateAction.REFUSE, "the draft case"


class TestADedicatedAgentIsAskedBeforeItsTask:
    """Owner decision 2026-10-31: one question before the task whenever a tool would ask.

    That answer covers the agent's calls and the task runs to completion; before, a
    server following its declarations turned the first sensitive inner call into a card
    and lost the rest of the task (lot 0, H1 and H3).
    """

    @staticmethod
    def _individual(annotations: dict[str, Any] | None, *, never: bool = False) -> ToolManifest:
        return build_mcp_tool_manifest(
            "mcp_user_770baa3e_x",
            "mcp_notes_agent",
            "x",
            "A tool",
            _SCHEMA,
            [],
            False,
            annotations=annotations,
            mcp_origin="user",
            mcp_server_key=str(_SERVER_ID),
            standing_approval=never,
        )

    def test_one_tool_that_would_ask_makes_the_task_ask(self) -> None:
        tools = [
            self._individual({"read_only_hint": True}),
            self._individual({"destructive_hint": True}),
        ]

        assert task_requires_confirmation(tools) is True

    def test_tools_that_ask_nothing_leave_the_task_unasked(self) -> None:
        tools = [
            self._individual({"read_only_hint": True}),
            self._individual({"read_only_hint": False, "destructive_hint": False}),
        ]

        assert task_requires_confirmation(tools) is False

    def test_a_never_ask_tool_does_not_make_the_task_ask(self) -> None:
        tools = [self._individual({"destructive_hint": True}, never=True)]

        assert task_requires_confirmation(tools) is False
