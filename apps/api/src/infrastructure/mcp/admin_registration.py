"""Register one admin MCP server under its already allocated routing identity."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

import structlog

from src.core.constants import (
    MCP_ITERATIVE_TASK_SUFFIX,
    MCP_REFERENCE_TOOL_NAME,
    MCP_TOOL_NAME_PREFIX,
)
from src.domains.agents.registry.catalogue import AgentManifest, ToolManifest
from src.infrastructure.mcp.schemas import MCPDiscoveredTool, MCPServerConfig
from src.infrastructure.mcp.security import resolve_hitl_requirement
from src.infrastructure.mcp.utils import is_app_only

if TYPE_CHECKING:
    from src.domains.agents.registry.agent_registry import AgentRegistry
    from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

logger = structlog.get_logger(__name__)


class StandardManifestBuilder(Protocol):
    def __call__(
        self,
        discovered: MCPDiscoveredTool,
        adapter_name: str,
        hitl_required: bool,
        agent_name: str,
        *,
        server_key: str,
    ) -> ToolManifest: ...


@dataclass(frozen=True)
class AdminRegistrationPorts:
    """Existing registration boundaries, kept injectable for startup composition."""

    standard_manifest: StandardManifestBuilder
    task_manifest: Callable[[str, str, str, str], ToolManifest]
    register_task: Callable[[str, str, str], bool]
    register_adapter: Callable[[MCPToolAdapter], None]


@dataclass(frozen=True)
class AdminServer:
    """Exact configured identity and independently allocated routing domain."""

    key: str
    domain: str
    description: str
    tools: list[MCPDiscoveredTool]
    config: MCPServerConfig | None
    aliases: Mapping[str, str] = field(default_factory=dict)
    task_alias: str | None = None

    @property
    def agent_name(self) -> str:
        return f"{self.domain}_agent"

    def tool_name(self, rpc_name: str) -> str:
        return self.aliases.get(rpc_name, f"{MCP_TOOL_NAME_PREFIX}_{self.key}_{rpc_name}")


def _visible_tools(
    server: AdminServer, reference_content: Mapping[str, str]
) -> list[MCPDiscoveredTool]:
    return [tool for tool in server.tools if _tool_is_visible(tool, server.key, reference_content)]


def _tool_is_visible(
    tool: MCPDiscoveredTool, server_key: str, reference_content: Mapping[str, str]
) -> bool:
    if is_app_only(tool.app_visibility):
        logger.info("mcp_tool_app_only_skipped", server=server_key, tool_name=tool.tool_name)
        return False
    if tool.tool_name == MCP_REFERENCE_TOOL_NAME and reference_content.get(server_key):
        logger.debug("mcp_tool_reference_skipped", server=server_key, tool_name=tool.tool_name)
        return False
    return True


def _register_standard_tool(
    registry: AgentRegistry,
    server: AdminServer,
    discovered: MCPDiscoveredTool,
    adapters: Mapping[str, MCPToolAdapter],
    ports: AdminRegistrationPorts,
    global_hitl_required: bool,
) -> int:
    name = server.tool_name(discovered.tool_name)
    adapter = adapters.get(name)
    if adapter is None:
        logger.warning("mcp_registration_adapter_missing", adapter_name=name)
        return 0
    hitl = (
        resolve_hitl_requirement(server.config, global_hitl_required)
        if server.config
        else global_hitl_required
    )
    manifest = ports.standard_manifest(
        discovered=discovered,
        adapter_name=name,
        hitl_required=hitl,
        agent_name=server.agent_name,
        server_key=server.key,
    )
    registry.register_tool_manifest(manifest)
    registry.register_tool_instance(name, adapter)
    ports.register_adapter(adapter)
    return 1


def _register_standard_server(
    registry: AgentRegistry,
    server: AdminServer,
    adapters: Mapping[str, MCPToolAdapter],
    ports: AdminRegistrationPorts,
    reference_content: Mapping[str, str],
    global_hitl_required: bool,
) -> int:
    tools = [
        tool
        for tool in _visible_tools(server, reference_content)
        if server.tool_name(tool.tool_name) in adapters
    ]
    if not tools:
        return 0
    names = [server.tool_name(tool.tool_name) for tool in tools]
    registry.register_agent_manifest(
        AgentManifest(name=server.agent_name, description=server.description, tools=names)
    )
    registered = sum(
        _register_standard_tool(registry, server, tool, adapters, ports, global_hitl_required)
        for tool in tools
    )
    logger.info(
        "mcp_server_registered",
        server=server.key,
        domain=server.domain,
        agent=server.agent_name,
        tools_count=len(names),
    )
    return registered


def _register_iterative_server(
    registry: AgentRegistry,
    server: AdminServer,
    adapters: Mapping[str, MCPToolAdapter],
    ports: AdminRegistrationPorts,
) -> int:
    registered = 0
    for tool in _visible_tools(server, {}):
        adapter = adapters.get(server.tool_name(tool.tool_name))
        if adapter is not None:
            ports.register_adapter(adapter)
            registered += 1
    if not registered:
        return 0
    name = server.task_alias or f"{MCP_TOOL_NAME_PREFIX}_{server.key}{MCP_ITERATIVE_TASK_SUFFIX}"
    if not ports.register_task(name, server.key, server.description):
        return 0
    manifest = ports.task_manifest(name, server.agent_name, server.key, server.description)
    registry.register_agent_manifest(
        AgentManifest(name=server.agent_name, description=server.description, tools=[name])
    )
    registry.register_tool_manifest(manifest)
    logger.info(
        "mcp_server_registered_iterative",
        server=server.key,
        domain=server.domain,
        agent=server.agent_name,
        individual_tools=registered,
    )
    return registered


def register_admin_server(
    registry: AgentRegistry,
    server: AdminServer,
    adapters: Mapping[str, MCPToolAdapter],
    ports: AdminRegistrationPorts,
    reference_content: Mapping[str, str],
    global_hitl_required: bool,
    iterative_enabled: bool,
) -> int:
    """Register a server while preserving its exact tool/RPC names and confirmation policy."""
    iterative = bool(server.config and server.config.iterative_mode and iterative_enabled)
    if iterative:
        return _register_iterative_server(registry, server, adapters, ports)
    return _register_standard_server(
        registry, server, adapters, ports, reference_content, global_hitl_required
    )
