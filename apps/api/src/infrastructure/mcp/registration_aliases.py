"""Admin discovery aliases shared by construction and boot registration."""

from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING

from src.core.constants import MCP_REFERENCE_TOOL_NAME
from src.infrastructure.mcp.schemas import MCPDiscoveredTool
from src.infrastructure.mcp.tool_aliases import allocate_tool_aliases
from src.infrastructure.mcp.utils import is_app_only

if TYPE_CHECKING:
    from src.infrastructure.mcp.tool_adapter import MCPToolAdapter


def admin_tool_aliases(
    discovered: Mapping[str, list[MCPDiscoveredTool]], *, reserved: Collection[str] = ()
) -> dict[tuple[str, str], str]:
    return allocate_tool_aliases(
        {
            (server, tool.tool_name): f"mcp_{server}_{tool.tool_name}"
            for server, tools in discovered.items()
            for tool in tools
        },
        reserved=reserved,
    )


def admin_task_aliases(
    server_keys: Collection[str], *, reserved: Collection[str] = ()
) -> dict[str, str]:
    allocated = allocate_tool_aliases(
        {(key, "__delegation__"): f"mcp_{key}_task" for key in server_keys}, reserved=reserved
    )
    return {key: allocated[(key, "__delegation__")] for key in server_keys}


def adapt_admin_aliases(
    adapters: Mapping[str, MCPToolAdapter], aliases: Mapping[tuple[str, str], str]
) -> dict[str, MCPToolAdapter]:
    """Select by the actual exact server/RPC pair, never an ambiguous concatenation."""
    adapted: dict[str, MCPToolAdapter] = {}
    for adapter in adapters.values():
        name = aliases[(adapter.server_name, adapter.mcp_tool_name)]
        adapted[name] = (
            adapter if adapter.name == name else adapter.model_copy(update={"name": name})
        )
    return adapted


def usable_admin_discoveries(
    server: str,
    tools: list[MCPDiscoveredTool],
    adapters: Mapping[str, MCPToolAdapter],
    aliases: Mapping[tuple[str, str], str],
    *,
    skip_reference: bool,
) -> list[MCPDiscoveredTool]:
    return [
        tool
        for tool in tools
        if aliases[(server, tool.tool_name)] in adapters
        and not is_app_only(tool.app_visibility)
        and not (skip_reference and tool.tool_name == MCP_REFERENCE_TOOL_NAME)
    ]
