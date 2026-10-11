"""Real admin registration publishes only callable, model-visible server capabilities."""

import builtins
from collections.abc import Iterator, Mapping, Sequence
from types import ModuleType
from unittest.mock import patch

import pytest
from pydantic import JsonValue

from src.core.config import settings
from src.core.context import (
    admin_mcp_disabled_ctx,
    build_request_tool_manifests,
    user_mcp_tools_ctx,
)
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.tools import tool_registry
from src.infrastructure.mcp import registration
from src.infrastructure.mcp.schemas import MCPDiscoveredTool, MCPServerConfig, MCPTransportType
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_catalogues(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(registration, "_admin_mcp_domains", {})
    monkeypatch.setattr(registration, "_admin_mcp_server_domains", {})
    monkeypatch.setattr(tool_registry, "_TOOL_REGISTRY", {})
    monkeypatch.setattr(tool_registry, "_INITIALIZED", True)
    monkeypatch.setattr(settings, "mcp_react_enabled", True)
    token = admin_mcp_disabled_ctx.set(None)
    user_token = user_mcp_tools_ctx.set(None)
    try:
        yield
    finally:
        user_mcp_tools_ctx.reset(user_token)
        admin_mcp_disabled_ctx.reset(token)


def _tool(server: str, name: str, *, app_only: bool = False) -> MCPDiscoveredTool:
    return MCPDiscoveredTool(
        server_name=server,
        tool_name=name,
        description=f"Capability {name}",
        input_schema={"type": "object", "properties": {}},
        app_visibility=["app"] if app_only else None,
    )


def _config(*, iterative: bool = False) -> MCPServerConfig:
    return MCPServerConfig(
        transport=MCPTransportType.STDIO,
        command="unused-test-command",
        iterative_mode=iterative,
        hitl_required=False,
    )


def _assert_published(
    registry: AgentRegistry,
    expected: dict[str, set[str]],
    *,
    iterative: bool = False,
) -> None:
    server_domains = registration.get_admin_mcp_server_domains()
    assert set(server_domains) == set(expected)
    assert set(registration.get_admin_mcp_domains()) == set(server_domains.values())
    agents = {manifest.name: manifest for manifest in registry.list_agent_manifests()}
    assert set(agents) == {f"{domain}_agent" for domain in server_domains.values()}
    manifests = registry.list_tool_manifests()
    assert all(manifest.mcp_origin == "admin" for manifest in manifests)
    assert {manifest.mcp_server_key for manifest in manifests} == set(expected)
    for key, domain in server_domains.items():
        _assert_agent_tools(registry, f"{domain}_agent", expected[key], iterative=iterative)


def _rpc_names(names: set[str]) -> set[str]:
    result: set[str] = set()
    for name in names:
        instance = tool_registry.get_tool(name)
        assert isinstance(instance, MCPToolAdapter)
        result.add(instance.mcp_tool_name)
    return result


def _assert_agent_tools(
    registry: AgentRegistry, agent_name: str, expected_rpcs: set[str], *, iterative: bool
) -> None:
    agent = registry.get_agent_manifest(agent_name)
    manifests = registry.list_tool_manifests(agent=agent_name)
    names = {manifest.name for manifest in manifests}
    assert set(agent.tools) == names
    assert all(tool_registry.get_tool(name) is not None for name in names)
    if iterative:
        assert len(names) == 1
        assert all(manifest.delegates_execution for manifest in manifests)
    else:
        assert _rpc_names(names) == expected_rpcs


def test_standard_partial_adapter_set_has_no_phantom_agent_tools() -> None:
    tools = {"Flights-v2": [_tool("Flights-v2", "search"), _tool("Flights-v2", "missing")]}
    adapters = registration.build_mcp_adapters(tools)
    adapters = {
        name: adapter for name, adapter in adapters.items() if adapter.mcp_tool_name == "search"
    }
    registry = AgentRegistry()
    count = registration.register_mcp_tools(registry, tools, adapters, {}, False)
    assert count == 1
    _assert_published(registry, {"Flights-v2": {"search"}})
    description = next(iter(registration.get_admin_mcp_domains().values()))
    assert "missing" not in description and "search" in description


@pytest.mark.parametrize("mode", ["missing", "empty", "app_only", "reference_prefetched"])
def test_unusable_standard_server_is_absent_while_healthy_server_remains(mode: str) -> None:
    broken = {
        "missing": [_tool("Broken", "lost")],
        "empty": [],
        "app_only": [_tool("Broken", "iframe", app_only=True)],
        "reference_prefetched": [_tool("Broken", "read_me")],
    }[mode]
    tools = {"Healthy": [_tool("Healthy", "search")], "Broken": broken}
    adapters = registration.build_mcp_adapters(tools)
    if mode == "missing":
        adapters = {
            name: adapter for name, adapter in adapters.items() if adapter.server_name != "Broken"
        }
    references = {"Broken": "Already injected reference"} if mode == "reference_prefetched" else {}
    registry = AgentRegistry()
    count = registration.register_mcp_tools(registry, tools, adapters, {}, False, references)
    assert count == 1
    _assert_published(registry, {"Healthy": {"search"}})


def test_no_adapters_means_no_server_domains_or_manifests() -> None:
    registry = AgentRegistry()
    count = registration.register_mcp_tools(
        registry, {"Broken": [_tool("Broken", "lost")]}, {}, {}, False
    )
    assert count == 0
    _assert_published(registry, {})


@pytest.mark.parametrize("iterative", [False, True])
def test_unbuildable_adapter_does_not_publish_a_dead_server(iterative: bool) -> None:
    original = MCPToolAdapter.from_mcp_tool

    def build(
        server_name: str,
        tool_name: str,
        description: str,
        input_schema: dict[str, JsonValue],
        app_resource_uri: str | None = None,
        output_schema: dict[str, object] | None = None,
    ) -> MCPToolAdapter:
        if server_name == "Broken":
            raise ValueError("Offline adapter construction failure")
        return original(
            server_name, tool_name, description, input_schema, app_resource_uri, output_schema
        )

    tools = {"Healthy": [_tool("Healthy", "search")], "Broken": [_tool("Broken", "lost")]}
    with patch.object(MCPToolAdapter, "from_mcp_tool", side_effect=build):
        adapters = registration.build_mcp_adapters(tools)
    registry = AgentRegistry()
    configs = {key: _config(iterative=iterative) for key in tools}
    count = registration.register_mcp_tools(registry, tools, adapters, configs, False)
    assert count == 1
    _assert_published(registry, {"Healthy": {"search"}}, iterative=iterative)


@pytest.mark.parametrize("mode", ["missing", "empty", "app_only"])
def test_iterative_proxy_requires_a_usable_individual_tool(mode: str) -> None:
    tools = {
        "Healthy": [_tool("Healthy", "search")],
        "Broken": {
            "missing": [_tool("Broken", "lost")],
            "empty": [],
            "app_only": [_tool("Broken", "iframe", app_only=True)],
        }[mode],
    }
    adapters = registration.build_mcp_adapters(tools)
    if mode == "missing":
        adapters = {
            name: adapter for name, adapter in adapters.items() if adapter.server_name != "Broken"
        }
    registry = AgentRegistry()
    configs = {key: _config(iterative=True) for key in tools}
    count = registration.register_mcp_tools(registry, tools, adapters, configs, False)
    assert count == 1
    _assert_published(registry, {"Healthy": {"search"}}, iterative=True)
    assert not any("Broken" in name for name in tool_registry.list_tool_names())


@pytest.mark.parametrize("prefetched", [False, True])
def test_iterative_reference_only_is_usable_when_the_reference_tool_is_callable(
    prefetched: bool,
) -> None:
    tools = {"Reference": [_tool("Reference", "read_me")]}
    adapters = registration.build_mcp_adapters(tools)
    registry = AgentRegistry()
    references = {"Reference": "Cached reference"} if prefetched else {}
    count = registration.register_mcp_tools(
        registry, tools, adapters, {"Reference": _config(iterative=True)}, False, references
    )
    assert count == 1
    _assert_published(registry, {"Reference": {"read_me"}}, iterative=True)
    assert any(
        isinstance(tool, MCPToolAdapter) and tool.mcp_tool_name == "read_me"
        for tool in tool_registry.get_all_tools().values()
    )


def test_disabling_exact_opaque_admin_key_withdraws_only_its_owned_manifests() -> None:
    tools = {"Flights-v2": [_tool("Flights-v2", "search")], "Other": [_tool("Other", "search")]}
    registry = AgentRegistry()
    registration.register_mcp_tools(
        registry, tools, registration.build_mcp_adapters(tools), {}, False
    )
    token = admin_mcp_disabled_ctx.set({"Flights-v2"})
    try:
        available = build_request_tool_manifests(registry)
        assert {manifest.mcp_server_key for manifest in available} == {"Other"}
    finally:
        admin_mcp_disabled_ctx.reset(token)


def _import_registration_failures() -> float:
    return sum(
        float(sample.value)
        for family in registration.mcp_tool_registration_failures_total.collect()
        for sample in family.samples
        if sample.name == "mcp_tool_registration_failures_total"
        and sample.labels == {"scope": "admin", "error_type": "ImportError"}
    )


@pytest.mark.parametrize("with_healthy_server", [False, True])
def test_a_missing_iterative_proxy_import_cannot_publish_a_dead_capability(
    monkeypatch: pytest.MonkeyPatch, with_healthy_server: bool
) -> None:
    original_import = builtins.__import__

    def missing_task_module(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> ModuleType:
        if name == "src.domains.agents.tools.mcp_react_tools":
            raise ImportError("Offline missing iterative task module")
        return original_import(name, globals, locals, fromlist, level)

    tools = {"Broken": [_tool("Broken", "read")]}
    configs = {"Broken": _config(iterative=True)}
    expected: dict[str, set[str]] = {}
    if with_healthy_server:
        tools["Healthy"] = [_tool("Healthy", "search")]
        expected["Healthy"] = {"search"}
    adapters = registration.build_mcp_adapters(tools)
    failures_before = _import_registration_failures()
    registry = AgentRegistry()
    monkeypatch.setattr(builtins, "__import__", missing_task_module)
    count = registration.register_mcp_tools(registry, tools, adapters, configs, False)
    assert count == len(expected)
    _assert_published(registry, expected)
    assert tool_registry.get_tool("mcp_Broken_task") is None
    assert _import_registration_failures() == failures_before + 1


def test_iterative_task_registration_reports_a_real_callable_success() -> None:
    name = "mcp_Fixture_task"
    assert registration._register_iterative_task_tool(name, "Fixture", "Read records") is True
    original = tool_registry.get_tool(name)
    assert original is not None
    assert registration._register_iterative_task_tool(name, "Fixture", "Read records") is True
    assert tool_registry.get_tool(name) is original
