"""An administrator's iterative server has one manifest per tool, offered through its task.

Spec D1 (2026-10-29). The planner sees an iterative server as ONE task tool;
its individual tools are reached through that task — by its sub-agent, by the
ReAct loop that expands it, and by the replay of a confirmed draft. Until this
lot an administrator's individuals had NO manifest at all: the gate read no
policy for them and a confirmed draft could not find them again (probes H3 and
P1, 2026-10-29). They now live in a reactive store, admitted only when the turn
offers their task — exactly like a personal server's individuals.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from src.core.config import settings
from src.core.context import build_request_tool_manifests, request_tool_manifests_ctx
from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.reactive_manifests import (
    reactive_manifest,
    register_reactive_manifest,
    reset_reactive_manifests,
)
from src.domains.agents.tools import tool_registry
from src.domains.agents.tools.tool_resolution import resolve_tool_instance
from src.infrastructure.mcp import registration
from src.infrastructure.mcp.registration import (
    build_mcp_adapters,
    build_mcp_tool_manifest,
    register_mcp_tools,
)
from src.infrastructure.mcp.schemas import MCPDiscoveredTool, MCPServerConfig, MCPTransportType
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

pytestmark = pytest.mark.unit

SERVER = "boards"
TASK = f"mcp_{SERVER}_task"
DROP, ADD, LIST = (f"mcp_{SERVER}_{tool}" for tool in ("drop_board", "add_card", "list_boards"))
_DESTRUCTIVE = {"destructive_hint": True, "read_only_hint": False}
_ADDITIVE = {"destructive_hint": False, "read_only_hint": False}


@pytest.fixture(autouse=True)
def isolated_boot_registration(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Both real registries, without importing every native provider tool."""
    monkeypatch.setattr(tool_registry, "_TOOL_REGISTRY", {})
    monkeypatch.setattr(tool_registry, "_INITIALIZED", True)
    monkeypatch.setattr(registration, "_admin_mcp_domains", {})
    monkeypatch.setattr(registration, "_admin_mcp_server_domains", {})
    monkeypatch.setattr(settings, "mcp_react_enabled", True)
    gate_runtime.reset_policy_cache()
    reset_reactive_manifests()
    yield
    reset_reactive_manifests()
    gate_runtime.reset_policy_cache()


def _tool(name: str, annotations: dict[str, Any] | None = None) -> MCPDiscoveredTool:
    return MCPDiscoveredTool(
        server_name=SERVER,
        tool_name=name,
        description=f"{name} on the boards server",
        input_schema={"type": "object", "properties": {}},
        annotations=annotations,
    )


def _register(*, hitl: bool | None, tools: list[MCPDiscoveredTool] | None = None) -> AgentRegistry:
    """Register the server through the real startup path (``register_mcp_tools``)."""
    listed = tools or [
        _tool("drop_board", _DESTRUCTIVE),
        _tool("add_card", _ADDITIVE),
        _tool("list_boards"),
    ]
    discovered = {SERVER: listed}
    config = MCPServerConfig(
        transport=MCPTransportType.STDIO,
        command="fixture-only",
        description="Boards and cards",
        iterative_mode=True,
        hitl_required=hitl,
    )
    registry = AgentRegistry()
    adapters = build_mcp_adapters(discovered)
    assert register_mcp_tools(registry, discovered, adapters, {SERVER: config}, False) == len(
        listed
    )
    return registry


def _task(registry: AgentRegistry) -> ToolManifest:
    return registry.get_tool_manifest(TASK)


class TestEachIndividualHasItsDeclaration:
    def test_admin_iterative_individual_has_a_policy_and_replays(self) -> None:
        registry = _register(hitl=False)
        offered = request_tool_manifests_ctx.set([_task(registry)])
        try:
            policies = {name: gate_runtime.resolve_policy(name) for name in (DROP, ADD, LIST)}
            instance = resolve_tool_instance(DROP)
        finally:
            request_tool_manifests_ctx.reset(offered)

        assert policies == {DROP: "confirm", ADD: "reversible", LIST: None}
        assert isinstance(instance, MCPToolAdapter), "a confirmed draft finds its tool again"
        assert instance.name == DROP and instance.server_name == SERVER

    def test_an_individual_is_out_of_reach_when_its_task_is_not_offered(self) -> None:
        """The account switched the server off: nothing of it may run or be replayed."""
        _register(hitl=False)
        offered = request_tool_manifests_ctx.set([])
        try:
            assert gate_runtime.resolve_policy(DROP) is None
            assert resolve_tool_instance(DROP) is None
        finally:
            request_tool_manifests_ctx.reset(offered)

    def test_no_individual_reaches_the_turn_catalogue(self) -> None:
        registry = _register(hitl=False)

        names = {manifest.name for manifest in build_request_tool_manifests(registry)}

        assert all(reactive_manifest(name) is not None for name in (DROP, ADD, LIST))
        assert TASK in names
        assert names.isdisjoint({DROP, ADD, LIST}), "the planner must see the task alone"


class TestTheTaskFollowsTheServerSetting:
    """An iterative server asks once, before its task, when one of its tools would.

    Spec D3, and the owner's decision of 2026-10-31 for a server following its
    declarations.
    """

    def test_a_server_with_confirmation_on_asks_before_its_task(self) -> None:
        task = _task(_register(hitl=True))

        assert task.permissions.hitl_required is True
        assert task.mutation_policy == "confirm"

    def test_a_server_with_confirmation_off_asks_before_its_task_when_a_tool_would(
        self,
    ) -> None:
        """Owner decision 2026-10-31: one question before the task, which then completes."""
        task = _task(_register(hitl=False))

        assert task.permissions.hitl_required is True
        assert task.mutation_policy == "confirm"

    def test_a_server_whose_tools_ask_nothing_leaves_its_task_unasked(self) -> None:
        task = _task(
            _register(hitl=False, tools=[_tool("add_card", _ADDITIVE), _tool("list_boards")])
        )

        assert task.permissions.hitl_required is False
        assert task.mutation_policy is None

    def test_every_individual_of_a_confirmed_server_owes_a_confirmation(self) -> None:
        registry = _register(hitl=True)
        offered = request_tool_manifests_ctx.set([_task(registry)])
        try:
            policies = {gate_runtime.resolve_policy(name) for name in (DROP, ADD, LIST)}
        finally:
            request_tool_manifests_ctx.reset(offered)

        assert policies == {"confirm"}


class TestTheStoreHoldsAdministratorIndividualsOnly:
    @pytest.mark.parametrize(
        ("origin", "server_key"),
        [("user", "8d2c0f3e-0000-0000-0000-000000000000"), ("admin", None)],
    )
    def test_it_refuses_a_manifest_without_an_administrator_server_identity(
        self, origin: Any, server_key: str | None
    ) -> None:
        manifest = build_mcp_tool_manifest(
            "mcp_user_8d2c0f3e_drop_board",
            "mcp_boards_agent",
            "drop_board",
            "Drop a board",
            {"type": "object", "properties": {}},
            [],
            False,
            mcp_origin=origin,
            mcp_server_key=server_key,
        )

        with pytest.raises(ValueError):
            register_reactive_manifest(manifest)
        assert reactive_manifest(manifest.name) is None
