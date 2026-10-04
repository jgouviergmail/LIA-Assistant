"""Application-authored MCP presentation identity, separate from server fields."""

from collections.abc import Mapping
from typing import TypedDict

from src.core.field_names import FIELD_DISPLAY_ONLY
from src.domains.agents.data_registry.models import RegistryItemType


class MCPSource(TypedDict):
    version: int
    server_name: str
    tool_name: str


def mcp_item_payload(
    item: Mapping[str, object], server_name: str, tool_name: str
) -> dict[str, object]:
    return {
        "server_name": server_name,
        "tool_name": tool_name,
        **item,
        "_mcp_structured": True,
        FIELD_DISPLAY_ONLY: mcp_source_display(server_name, tool_name),
    }


def mcp_source_display(server_name: str, tool_name: str) -> dict[str, object]:
    source: MCPSource = {"version": 1, "server_name": server_name, "tool_name": tool_name}
    return {"_mcp_source": source}


def source_identity(value: object) -> MCPSource | None:
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or value.get("version") != 1
    ):
        return None
    server, tool = value.get("server_name"), value.get("tool_name")
    if not isinstance(server, str) or not isinstance(tool, str):
        return None
    return {"version": 1, "server_name": server, "tool_name": tool}


def authoritative_mcp_source(item: object, display: Mapping[str, object]) -> MCPSource | None:
    """Historical registry metadata also wins over an externally forged marker."""
    kind = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
    if kind != RegistryItemType.MCP_RESULT:
        return None
    if source := source_identity(display.get("_mcp_source")):
        return source
    meta = item.get("meta") if isinstance(item, dict) else getattr(item, "meta", None)
    server = meta.get("source") if isinstance(meta, dict) else getattr(meta, "source", None)
    tool = meta.get("tool_name") if isinstance(meta, dict) else getattr(meta, "tool_name", None)
    return {
        "version": 1,
        "server_name": server.removeprefix("mcp_") if isinstance(server, str) else "MCP",
        "tool_name": tool if isinstance(tool, str) else "",
    }
