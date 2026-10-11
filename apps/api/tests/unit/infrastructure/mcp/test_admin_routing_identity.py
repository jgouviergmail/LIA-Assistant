"""Exact configured admin identities survive domain normalization and real registration."""

import re
from collections.abc import Iterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.context import admin_mcp_disabled_ctx, request_tool_manifests_ctx
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.domain_taxonomy import (
    collect_all_mcp_domains,
    deduplicate_mcp_slugs,
    filter_admin_mcp_disabled_manifests,
)
from src.domains.agents.services.analysis.domain_availability import build_available_domains
from src.domains.agents.tools import tool_registry
from src.domains.user_mcp.admin_router import list_admin_servers, toggle_admin_server
from src.domains.users.models import User
from src.infrastructure.mcp import registration
from src.infrastructure.mcp.client_manager import MCPClientManager
from src.infrastructure.mcp.registration import (
    build_mcp_adapters,
    build_mcp_tool_manifest,
    get_admin_mcp_domains,
    get_admin_mcp_server_domains,
    register_mcp_tools,
)
from src.infrastructure.mcp.schemas import MCPDiscoveredTool, MCPServerConfig, MCPTransportType
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_boot_registration(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Use both actual registries without importing unrelated native provider tools."""
    monkeypatch.setattr(tool_registry, "_TOOL_REGISTRY", {})
    monkeypatch.setattr(tool_registry, "_INITIALIZED", True)
    monkeypatch.setattr(registration, "_admin_mcp_domains", {})
    monkeypatch.setattr(registration, "_admin_mcp_server_domains", {})
    yield


def _register_servers(*names: str, iterative: bool = False) -> AgentRegistry:
    discovered = {
        name: [
            MCPDiscoveredTool(
                server_name=name,
                tool_name="search_flights",
                description=f"Flights from {name}",
                input_schema={"type": "object", "properties": {}},
            )
        ]
        for name in names
    }
    adapters = build_mcp_adapters(discovered)
    configs = {
        name: MCPServerConfig(
            transport=MCPTransportType.STDIO,
            command="fixture-only",
            description=f"Flights from {name}",
            iterative_mode=iterative,
        )
        for name in names
    }
    registry = AgentRegistry()
    assert register_mcp_tools(registry, discovered, adapters, configs, False) == len(names)
    return registry


def test_colliding_admin_labels_register_two_distinct_agents_and_keep_raw_rpc_names() -> None:
    registry = _register_servers("Flights-v2", "Flights v2")
    domains = get_admin_mcp_server_domains()
    assert len(set(domains.values())) == 2
    assert domains["Flights-v2"] == "mcp_flights_v2"
    assert {agent.name for agent in registry.list_agent_manifests()} == {
        f"{domain}_agent" for domain in domains.values()
    }
    manifests = registry.list_tool_manifests()
    assert {manifest.mcp_server_key for manifest in manifests} == {"Flights-v2", "Flights v2"}
    assert all(manifest.mcp_origin == "admin" for manifest in manifests)
    _assert_raw_rpc_names(registry, ("Flights-v2", "Flights v2"))


def _assert_raw_rpc_names(registry: AgentRegistry, keys: tuple[str, ...]) -> None:
    manifests = {manifest.mcp_server_key: manifest for manifest in registry.list_tool_manifests()}
    for key in keys:
        name = manifests[key].name
        assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name)
        if key == "Flights-v2":
            assert name == "mcp_Flights-v2_search_flights"
        adapter: object = tool_registry.get_tool(name)
        assert isinstance(adapter, MCPToolAdapter)
        assert adapter.server_name == key
        assert adapter.mcp_tool_name == "search_flights"
        assert registry.get_tool_instance(name) is adapter


def test_a_natural_suffix_cannot_collide_with_an_allocated_admin_suffix() -> None:
    registry = _register_servers("Flights-v2", "Flights v2", "Flights_v2_2")
    domains = get_admin_mcp_server_domains()
    assert len(set(domains.values())) == 3
    assert domains["Flights_v2_2"] == "mcp_flights_v2_2"
    assert len(registry.list_agent_manifests()) == 3


@pytest.mark.parametrize("disabled_key", ["Flights-v2", "Flights v2"])
def test_raw_disabled_key_removes_only_its_standard_manifest_and_routing_domain(
    disabled_key: str,
) -> None:
    registry = _register_servers("Flights-v2", "Flights v2")
    manifests = registry.list_tool_manifests()
    remaining = {"Flights-v2", "Flights v2"} - {disabled_key}
    visible = filter_admin_mcp_disabled_manifests(manifests, {disabled_key})
    assert {manifest.mcp_server_key for manifest in visible} == remaining
    snapshot = get_admin_mcp_server_domains()
    domains = collect_all_mcp_domains(
        get_admin_mcp_domains(), {disabled_key}, None, admin_server_domains=snapshot
    )
    assert {item["name"] for item in domains} == {snapshot[key] for key in remaining}


def test_iterative_manifest_carries_exact_admin_key_and_stays_disabled_after_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mcp_react_enabled", True)
    registry = _register_servers("Flights-v2", "Flights v2", iterative=True)
    manifests = registry.list_tool_manifests()
    assert len({manifest.name for manifest in manifests}) == 2
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", manifest.name) for manifest in manifests)
    assert (
        next(m for m in manifests if m.mcp_server_key == "Flights-v2").name == "mcp_Flights-v2_task"
    )
    assert all(manifest.mcp_origin == "admin" for manifest in manifests)
    assert {manifest.mcp_server_key for manifest in manifests} == {"Flights-v2", "Flights v2"}
    assert [
        manifest.mcp_server_key
        for manifest in filter_admin_mcp_disabled_manifests(manifests, {"Flights-v2"})
    ] == ["Flights v2"]
    assert all(tool_registry.get_tool(manifest.name) is not None for manifest in manifests)


def test_explicit_user_identity_never_inherits_an_admin_switch_even_with_legacy_equal_domain() -> (
    None
):
    registry = _register_servers("Flights-v2")
    domain = get_admin_mcp_server_domains()["Flights-v2"]
    user = build_mcp_tool_manifest(
        "mcp_user_fixture_search_flights",
        f"{domain}_agent",
        "search_flights",
        "User flights",
        {"type": "object", "properties": {}},
        [],
        False,
        mcp_origin="user",
        mcp_server_key="11111111-2222-3333-4444-555555555555",
    )
    assert filter_admin_mcp_disabled_manifests(
        [*registry.list_tool_manifests(), user], {"Flights-v2"}
    ) == [user]


def test_admin_snapshot_reserves_domains_for_user_allocation_and_returns_copies() -> None:
    _register_servers("Flights-v2")
    snapshot = get_admin_mcp_server_domains()
    user = deduplicate_mcp_slugs(["Flights v2"], reserved=set(snapshot.values()))
    assert user["Flights v2"] not in snapshot.values()
    snapshot["Flights-v2"] = "mcp_changed_by_caller"
    assert get_admin_mcp_server_domains()["Flights-v2"] == "mcp_flights_v2"


def test_empty_boot_registration_clears_both_admin_snapshots() -> None:
    _register_servers("Flights-v2")
    assert register_mcp_tools(AgentRegistry(), {}, {}, {}, False) == 0
    assert get_admin_mcp_domains() == {}
    assert get_admin_mcp_server_domains() == {}


def _install_discovered_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = MCPClientManager()
    discovered = {
        key: [
            MCPDiscoveredTool(
                server_name=key,
                tool_name="search_flights",
                description=f"Flights from {key}",
                input_schema={"type": "object", "properties": {}},
            )
        ]
        for key in ("Flights-v2", "Flights v2")
    }
    monkeypatch.setattr(manager, "_discovered_tools", discovered)
    monkeypatch.setattr(
        "src.infrastructure.mcp.client_manager.get_mcp_client_manager", lambda: manager
    )


@pytest.mark.asyncio
async def test_admin_list_uses_each_registered_domain_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_servers("Flights-v2", "Flights v2")
    _install_discovered_manager(monkeypatch)
    user = User(id=uuid4(), email="fixture@example.test", admin_mcp_disabled_servers=[])
    responses = await list_admin_servers(user=user)
    assert {response.server_key: response.description for response in responses} == {
        "Flights-v2": "Flights from Flights-v2",
        "Flights v2": "Flights from Flights v2",
    }


@pytest.mark.asyncio
async def test_real_toggle_preserves_raw_key_and_removes_only_its_available_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _register_servers("Flights-v2", "Flights v2")
    _install_discovered_manager(monkeypatch)
    user = User(
        id=uuid4(),
        email="fixture@example.test",
        is_active=True,
        deleted_at=None,
        admin_mcp_disabled_servers=[],
    )
    db = AsyncSession()
    queried = AsyncMock(return_value=user)
    committed = AsyncMock()
    monkeypatch.setattr(db, "scalar", queried)
    monkeypatch.setattr(db, "commit", committed)
    response = await toggle_admin_server(server_key="Flights v2", user=user, db=db)
    assert response.server_key == "Flights v2"
    assert response.enabled_for_user is False
    assert user.admin_mcp_disabled_servers == ["Flights v2"]
    queried.assert_awaited_once()
    committed.assert_awaited_once()
    disabled_token = admin_mcp_disabled_ctx.set(set(user.admin_mcp_disabled_servers))
    manifests_token = request_tool_manifests_ctx.set(registry.list_tool_manifests())
    try:
        domains = build_available_domains()
        assert {item["name"] for item in domains if item["name"].startswith("mcp")} == {
            get_admin_mcp_server_domains()["Flights-v2"]
        }
    finally:
        request_tool_manifests_ctx.reset(manifests_token)
        admin_mcp_disabled_ctx.reset(disabled_token)
    restored = await toggle_admin_server(server_key="Flights v2", user=user, db=db)
    assert restored.enabled_for_user is True
    assert user.admin_mcp_disabled_servers == []
