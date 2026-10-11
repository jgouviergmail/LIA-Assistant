"""The callable's actual server must match the available manifest's exact identity."""

import re
from collections.abc import Iterator
from dataclasses import replace
from uuid import UUID

import pytest
from langchain_core.tools import StructuredTool

from src.core.config import settings
from src.core.context import (
    UserMCPToolsContext,
    admin_mcp_disabled_ctx,
    request_tool_manifests_ctx,
    user_mcp_tools_ctx,
)
from src.core.i18n import language_scope
from src.domains.agents.effects import runtime as effect_runtime
from src.domains.agents.effects.confirmation import execute_tool_call_draft, readable_tool_name
from src.domains.agents.registry import manifest_resolution
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import ToolManifest, get_tool_category
from src.domains.agents.registry.domain_taxonomy import filter_admin_mcp_disabled_manifests
from src.domains.agents.tools import tool_registry
from src.domains.agents.tools.mcp_react_tools import (
    _get_mcp_server_tools_for_react,
    _get_user_mcp_server_tools_for_react,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.tool_resolution import (
    resolve_tool_instance,
    resolve_tool_manifest,
)
from src.infrastructure.mcp import registration
from src.infrastructure.mcp.registration import (
    build_mcp_adapters,
    build_mcp_tool_manifest,
    register_mcp_tools,
)
from src.infrastructure.mcp.schemas import MCPDiscoveredTool, MCPServerConfig, MCPTransportType
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from tests.unit.domains.user_mcp.test_user_catalogue_routing import RoutingHarness
from tests.unit.domains.user_mcp.test_user_catalogue_routing import routing as routing

pytestmark = pytest.mark.unit
OWNER = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
FIRST = UUID("11111111-2222-3333-4444-555555555555")
SECOND = UUID("11111111-9222-3333-4444-555555555555")


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[AgentRegistry]:
    instance = AgentRegistry()
    monkeypatch.setattr(tool_registry, "_TOOL_REGISTRY", {})
    monkeypatch.setattr(manifest_resolution, "get_global_registry", lambda: instance)
    monkeypatch.setattr(registration, "_admin_mcp_domains", {})
    monkeypatch.setattr(registration, "_admin_mcp_server_domains", {})
    user_token = user_mcp_tools_ctx.set(None)
    offered_token = request_tool_manifests_ctx.set(None)
    disabled_token = admin_mcp_disabled_ctx.set(set())
    try:
        yield instance
    finally:
        admin_mcp_disabled_ctx.reset(disabled_token)
        request_tool_manifests_ctx.reset(offered_token)
        user_mcp_tools_ctx.reset(user_token)


def _admin(registry: AgentRegistry, servers: dict[str, str]) -> list[ToolManifest]:
    discovered = {
        key: [
            MCPDiscoveredTool(
                server_name=key,
                tool_name=rpc,
                description="Identity fixture",
                input_schema={"type": "object", "properties": {}},
            )
        ]
        for key, rpc in servers.items()
    }
    adapters = build_mcp_adapters(discovered)
    assert len(adapters) == len(servers), "discovery must not overwrite another server's adapter"
    assert register_mcp_tools(registry, discovered, adapters, {}, False) == len(servers)
    return registry.list_tool_manifests()


def _user(server_id: UUID = FIRST) -> tuple[UserMCPToolAdapter, ToolManifest]:
    adapter = UserMCPToolAdapter.from_discovered_tool(
        server_id, OWNER, "Personal flights", "search_flights", "Personal flights", {}
    )
    manifest = build_mcp_tool_manifest(
        adapter.name,
        "mcp_personal_agent",
        adapter.mcp_tool_name,
        adapter.description,
        {},
        [],
        False,
        mcp_origin="user",
        mcp_server_key=str(server_id),
    )
    return adapter, manifest


def test_disabled_admin_alias_cannot_replace_the_offered_personal_callable(
    registry: AgentRegistry,
) -> None:
    admin = _admin(registry, {"user_11111111": "search_flights"})
    adapter, manifest = _user()
    ctx = UserMCPToolsContext(tool_manifests=[manifest], tool_instances={adapter.name: adapter})
    user_mcp_tools_ctx.set(ctx)
    offered = filter_admin_mcp_disabled_manifests([*admin, manifest], {"user_11111111"})
    assert offered == [manifest]
    request_tool_manifests_ctx.set(offered)
    assert resolve_tool_manifest(adapter.name) is manifest
    assert resolve_tool_instance(adapter.name) is adapter
    assert resolve_tool_instance(f"{adapter.name}_tool") is adapter


def test_an_ambiguous_legacy_alias_fails_closed_instead_of_selecting_a_server(
    registry: AgentRegistry,
) -> None:
    admin = _admin(registry, {"user_11111111": "search_flights"})
    adapter, manifest = _user()
    user_mcp_tools_ctx.set(
        UserMCPToolsContext(tool_manifests=[manifest], tool_instances={adapter.name: adapter})
    )
    request_tool_manifests_ctx.set([*admin, manifest])
    assert resolve_tool_manifest(adapter.name) is None
    assert resolve_tool_instance(adapter.name) is None


def test_an_explicit_empty_catalogue_cannot_resurrect_a_global_admin(
    registry: AgentRegistry,
) -> None:
    manifest = _admin(registry, {"Flights": "search_flights"})[0]
    request_tool_manifests_ctx.set([])
    assert resolve_tool_manifest(manifest.name) is None
    assert resolve_tool_instance(manifest.name) is None


def test_a_personal_adapter_for_another_exact_uuid_is_refused(registry: AgentRegistry) -> None:
    adapter, manifest = _user()
    mismatched = replace(manifest, mcp_server_key=str(SECOND))
    user_mcp_tools_ctx.set(
        UserMCPToolsContext(tool_manifests=[mismatched], tool_instances={adapter.name: adapter})
    )
    request_tool_manifests_ctx.set([mismatched])
    assert resolve_tool_instance(adapter.name) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("iterative", [False, True])
async def test_actual_setup_preserves_two_servers_with_the_same_first_eight_uuid_characters(
    routing: RoutingHarness, registry: AgentRegistry, iterative: bool
) -> None:
    first = routing.server(
        "First", [{"name": "search", "description": "Read first"}], iterative=iterative
    )
    second = routing.server(
        "Second", [{"name": "search", "description": "Read second"}], iterative=iterative
    )
    first.id, second.id = FIRST, SECOND
    ctx = await routing.context()
    assert len(ctx.tool_manifests) == 2
    individuals = [
        tool for tool in ctx.tool_instances.values() if isinstance(tool, UserMCPToolAdapter)
    ]
    assert {tool.server_id for tool in individuals} == {FIRST, SECOND}
    assert len({tool.name for tool in individuals}) == 2
    assert all(tool.mcp_tool_name == "search" for tool in individuals)
    before = {tool.server_id: tool.name for tool in individuals}
    routing.servers.reverse()
    rebuilt = await routing.context()
    assert {
        tool.server_id: tool.name
        for tool in rebuilt.tool_instances.values()
        if isinstance(tool, UserMCPToolAdapter)
    } == before


@pytest.mark.asyncio
async def test_actual_setup_allocates_a_personal_alias_outside_the_admin_namespace(
    routing: RoutingHarness, registry: AgentRegistry
) -> None:
    admin = _admin(registry, {"user_11111111": "search_flights"})[0]
    server = routing.server("Personal", [{"name": "search_flights", "description": "Personal"}])
    server.id = FIRST
    ctx = await routing.context()
    assert ctx.tool_manifests[0].name != admin.name
    user_mcp_tools_ctx.set(ctx)
    request_tool_manifests_ctx.set([admin, *ctx.tool_manifests])
    user = resolve_tool_instance(ctx.tool_manifests[0].name)
    assert isinstance(user, UserMCPToolAdapter)
    assert user.server_id == FIRST
    assert user.mcp_tool_name == "search_flights"
    assert resolve_tool_instance(admin.name) is tool_registry.get_tool(admin.name)


def test_compound_admin_key_and_rpc_collisions_keep_both_actual_servers(
    registry: AgentRegistry,
) -> None:
    manifests = _admin(registry, {"a_b": "c", "a": "b_c"})
    assert len({manifest.name for manifest in manifests}) == 2
    request_tool_manifests_ctx.set(manifests)
    for manifest in manifests:
        adapter = resolve_tool_instance(manifest.name)
        assert isinstance(adapter, MCPToolAdapter)
        assert adapter.server_name == manifest.mcp_server_key


def test_an_admin_iterative_selector_never_includes_another_server_with_a_shared_prefix(
    registry: AgentRegistry,
) -> None:
    _admin(registry, {"a": "search", "a_b": "other"})
    wrappers = _get_mcp_server_tools_for_react("a")
    assert [wrapper.name for wrapper in wrappers] == ["search"]


@pytest.mark.asyncio
async def test_confirmation_replay_invokes_the_offered_personal_adapter_and_keeps_its_label(
    registry: AgentRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = _admin(registry, {"user_11111111": "search_flights"})
    adapter, manifest = _user()
    user_mcp_tools_ctx.set(
        UserMCPToolsContext(tool_manifests=[manifest], tool_instances={adapter.name: adapter})
    )
    request_tool_manifests_ctx.set(
        filter_admin_mcp_disabled_manifests([*admin, manifest], {"user_11111111"})
    )
    called: list[tuple[UUID, UUID, str]] = []

    async def personal_call(tool: UserMCPToolAdapter, **arguments: object) -> dict[str, object]:
        called.append((tool.user_id, tool.server_id, tool.mcp_tool_name))
        return {"success": True}

    monkeypatch.setattr(UserMCPToolAdapter, "_call_server", personal_call)
    monkeypatch.setattr(effect_runtime, "resolve_policy", lambda _name: "read")
    result = await execute_tool_call_draft(
        {"tool_name": adapter.name, "tool_args": {}, "draft_id": "identity-fixture"}, OWNER, None
    )
    assert result["success"] is True
    assert called == [(OWNER, FIRST, "search_flights")]
    assert readable_tool_name(adapter.name, language="en") == "Personal flights: search flights"


@pytest.mark.asyncio
async def test_confirmation_replay_cannot_execute_an_admin_absent_from_the_snapshot(
    registry: AgentRegistry,
) -> None:
    manifest = _admin(registry, {"Flights": "search_flights"})[0]
    request_tool_manifests_ctx.set([])
    result = await execute_tool_call_draft(
        {"tool_name": manifest.name, "tool_args": {}, "draft_id": "disabled-fixture"}, OWNER, None
    )
    assert result["success"] is False


@pytest.mark.parametrize(
    "server,rpc",
    [
        ("Catalogue Polaris", "read.record"),
        ("!", "read_record"),
        ("long_" * 30, "delete_record"),
        ("Bank", "read_" * 30),
    ],
)
def test_model_aliases_are_valid_and_bounded_while_exact_server_and_rpc_are_preserved(
    registry: AgentRegistry, server: str, rpc: str
) -> None:
    manifest = _admin(registry, {server: rpc})[0]
    request_tool_manifests_ctx.set([manifest])
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", manifest.name)
    adapter = resolve_tool_instance(manifest.name)
    assert isinstance(adapter, MCPToolAdapter)
    assert adapter.server_name == server
    assert adapter.mcp_tool_name == rpc
    if rpc == "delete_record":
        assert get_tool_category(manifest) == "delete", "alias truncation must not hide a mutation"
    assert readable_tool_name(manifest.name, language="en") == (
        f"{server}: {rpc.replace('_', ' ').strip()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("iterative", [False, True])
async def test_natural_rpc_alias_cannot_overwrite_a_normalized_rpc_alias(
    routing: RoutingHarness, registry: AgentRegistry, iterative: bool
) -> None:
    collision = UserMCPToolAdapter.from_discovered_tool(
        FIRST, OWNER, "Bank", "a.b", "First RPC", {}
    ).name.removeprefix("mcp_user_11111111_")
    server = routing.server(
        "Bank",
        [
            {"name": "a.b", "description": "First RPC"},
            {"name": collision, "description": "Second RPC"},
        ],
        iterative=iterative,
    )
    server.id = FIRST
    ctx = await routing.context()
    adapters = [
        tool for tool in ctx.tool_instances.values() if isinstance(tool, UserMCPToolAdapter)
    ]
    assert len(adapters) == 2
    assert len({tool.name for tool in adapters}) == 2
    assert {tool.mcp_tool_name for tool in adapters} == {"a.b", collision}
    if iterative:
        user_mcp_tools_ctx.set(ctx)
        wrappers = _get_user_mcp_server_tools_for_react("11111111")
        assert len({wrapper.name for wrapper in wrappers}) == 2
        assert {wrapper._inner.mcp_tool_name for wrapper in wrappers} == {"a.b", collision}


@pytest.mark.asyncio
async def test_iterative_rpc_named_task_remains_callable_beside_its_delegation_door(
    routing: RoutingHarness, registry: AgentRegistry
) -> None:
    server = routing.server("Bank", [{"name": "task", "description": "Native RPC"}], iterative=True)
    server.id = FIRST
    ctx = await routing.context()
    assert len(ctx.tool_instances) == 2
    adapter = next(
        tool for tool in ctx.tool_instances.values() if isinstance(tool, UserMCPToolAdapter)
    )
    assert adapter.name != ctx.tool_manifests[0].name
    assert adapter.mcp_tool_name == "task"


def test_native_confirmation_label_remains_a_pure_formatter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_lookup(_name: str) -> None:
        raise AssertionError("native labels must not resolve a tool")

    monkeypatch.setattr(
        "src.domains.agents.tools.tool_resolution.resolve_tool_instance", forbidden_lookup
    )
    assert readable_tool_name("delete_event_tool") == "delete event"


@pytest.mark.parametrize(
    "language,separator",
    [("en", ": "), ("fr", "\u00a0: "), ("zh-CN", "：")],
)
def test_exact_mcp_labels_follow_the_readers_declared_punctuation(
    registry: AgentRegistry, language: str, separator: str
) -> None:
    manifest = _admin(registry, {"Agence Rhône": "billing__cancel_subscription"})[0]
    request_tool_manifests_ctx.set([manifest])
    with language_scope(language):
        assert readable_tool_name(manifest.name) == (
            f"Agence Rhône{separator}billing cancel subscription"
        )


def test_an_explicit_reader_language_overrides_the_declared_language(
    registry: AgentRegistry,
) -> None:
    manifest = _admin(registry, {"Agence Rhône": "read_record"})[0]
    request_tool_manifests_ctx.set([manifest])
    with language_scope("fr"):
        assert readable_tool_name(manifest.name, language="en") == "Agence Rhône: read record"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "language,separator",
    [("en", ": "), ("fr", "\u00a0: "), ("zh-CN", "：")],
)
async def test_actual_admin_task_factory_preserves_display_identity_and_refuses_another_server(
    registry: AgentRegistry, monkeypatch: pytest.MonkeyPatch, language: str, separator: str
) -> None:
    monkeypatch.setattr(settings, "mcp_react_enabled", True)
    discovered = {
        "Canvas Orion": [
            MCPDiscoveredTool(
                server_name="Canvas Orion", tool_name="read", description="Read", input_schema={}
            )
        ]
    }
    assert (
        register_mcp_tools(
            registry,
            discovered,
            build_mcp_adapters(discovered),
            {
                "Canvas Orion": MCPServerConfig(
                    transport=MCPTransportType.STDIO, command="fixture-only", iterative_mode=True
                )
            },
            False,
        )
        == 1
    )
    manifest = registry.list_tool_manifests()[0]
    request_tool_manifests_ctx.set([manifest])
    assert readable_tool_name(manifest.name, language=language) == f"Canvas Orion{separator}task"
    task = resolve_tool_instance(manifest.name)
    assert isinstance(task, StructuredTool)
    coroutine = task.coroutine
    assert coroutine is not None
    monkeypatch.setattr(effect_runtime, "resolve_policy", lambda _name: "read")
    result: object = await coroutine(server_name="Wrong Server", task="ignored", runtime=None)
    assert isinstance(result, UnifiedToolOutput)
    assert result.success is False
    assert result.error_code == "INVALID_INPUT"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "language,separator",
    [("en", ": "), ("fr", "\u00a0: "), ("zh-CN", "：")],
)
async def test_actual_user_task_factory_targets_its_allocated_extended_prefix_and_real_label(
    routing: RoutingHarness,
    registry: AgentRegistry,
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    separator: str,
) -> None:
    first = routing.server("Bank First", [{"name": "read", "description": "Read"}], iterative=True)
    second = routing.server(
        "Bank Second", [{"name": "read", "description": "Read"}], iterative=True
    )
    first.id, second.id = FIRST, SECOND
    ctx = await routing.context()
    user_mcp_tools_ctx.set(ctx)
    request_tool_manifests_ctx.set(ctx.tool_manifests)
    first_manifest = next(item for item in ctx.tool_manifests if item.mcp_server_key == str(FIRST))
    second_manifest = next(
        item for item in ctx.tool_manifests if item.mcp_server_key == str(SECOND)
    )
    prefix = (
        next(
            parameter
            for parameter in second_manifest.parameters
            if parameter.name == "server_id_prefix"
        )
        .constraints[0]
        .value[0]
    )
    assert (
        readable_tool_name(first_manifest.name, language=language) == f"Bank First{separator}task"
    )
    task = resolve_tool_instance(first_manifest.name)
    assert isinstance(task, StructuredTool)
    coroutine = task.coroutine
    assert coroutine is not None
    monkeypatch.setattr(effect_runtime, "resolve_policy", lambda _name: "read")
    result: object = await coroutine(
        server_id_prefix=prefix, server_name="Bank First", task="ignored", runtime=None
    )
    assert isinstance(result, UnifiedToolOutput)
    assert result.success is False
    assert result.error_code == "INVALID_INPUT"
