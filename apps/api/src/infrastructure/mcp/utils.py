"""
MCP Shared Utilities.

Provides helpers shared by both admin and user MCP subsystems:
- ``extract_app_meta``: Extract MCP Apps metadata from SDK Tool objects.
- ``is_app_only``: Check if a tool is iframe-only (not exposed to LLM).
- ``build_mcp_app_output``: Build a UnifiedToolOutput for MCP Apps (interactive widgets).

Phase: evolution F2.5 — MCP Apps
Created: 2026-03-04
"""

from __future__ import annotations

import time
from typing import Any

from src.core.field_names import FIELD_REGISTRY_ID
from src.domains.agents.constants import CONTEXT_DOMAIN_MCP_APPS
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.tools.output import UnifiedToolOutput


def extract_app_meta(tool: Any) -> tuple[str | None, list[str] | None]:
    """Extract MCP Apps UI metadata from an MCP SDK Tool object.

    Reads ``Tool.meta.ui.resourceUri`` and ``Tool.meta.ui.visibility``
    as defined by the MCP Apps protocol (SEP-1865).

    Args:
        tool: MCP SDK ``Tool`` object from ``list_tools()``.

    Returns:
        Tuple of ``(resource_uri, visibility)`` where both can be ``None``
        when the tool has no MCP Apps UI associated.
    """
    meta = getattr(tool, "meta", None)
    if not isinstance(meta, dict):
        return None, None
    ui = meta.get("ui")
    if not isinstance(ui, dict):
        return None, None
    resource_uri = ui.get("resourceUri")
    visibility = ui.get("visibility")
    # Validate types
    if resource_uri is not None and not isinstance(resource_uri, str):
        return None, None
    if visibility is not None and not isinstance(visibility, list):
        return None, None
    return resource_uri, visibility


def is_app_only(visibility: list[str] | None) -> bool:
    """Check if a tool is app-only (iframe-only, not exposed to LLM catalogue).

    A tool with ``visibility == ["app"]`` is rendered only as an interactive
    iframe widget and should be skipped during LLM tool registration.

    Args:
        visibility: The ``app_visibility`` field from tool metadata.

    Returns:
        ``True`` if the tool is iframe-only.
    """
    return visibility is not None and set(visibility) == {"app"}


def build_mcp_app_output(
    *,
    raw_result: str,
    html_content: str,
    tool_name: str,
    adapter_name: str,
    server_display_name: str,
    server_id: str,
    server_key: str,
    server_source: str,
    resource_uri: str,
    source_label: str,
    tool_arguments: dict[str, object] | None = None,
    tool_input_schema: dict[str, object] | None = None,
) -> UnifiedToolOutput:
    """Build a UnifiedToolOutput for an MCP Apps interactive widget.

    Shared by both ``MCPToolAdapter`` (admin) and ``UserMCPToolAdapter`` (user)
    to avoid duplication of MCP_APP RegistryItem construction logic.

    Args:
        raw_result: Raw text result from ``call_tool()``.
        html_content: HTML content fetched from ``read_resource()``.
        tool_name: MCP tool name (e.g., ``create_view``).
        adapter_name: Prefixed adapter name (e.g., ``mcp_excalidraw_create_view``).
        server_display_name: Human-readable server name (for card badge).
        server_id: UUID string for user MCP servers, ``""`` for admin.
        server_key: String key for admin MCP servers, ``""`` for user.
        server_source: ``"user"`` or ``"admin"``.
        resource_uri: The ``ui://`` URI used to fetch the HTML.
        source_label: Prometheus-style label for the ``meta.source`` field.
        tool_arguments: Original tool call arguments (for ``ui/notifications/tool-input``).
        tool_input_schema: JSON Schema of the tool's input parameters.

    Returns:
        ``UnifiedToolOutput`` with a single ``MCP_APP`` RegistryItem.
    """
    unique_key = f"{server_source}_{server_key or server_id}_{tool_name}_{time.time_ns()}"
    rid = generate_registry_id(RegistryItemType.MCP_APP, unique_key)

    registry_item = RegistryItem(
        id=rid,
        type=RegistryItemType.MCP_APP,
        payload={
            FIELD_REGISTRY_ID: rid,  # Needed by McpAppSentinel to emit data-registry-id attr
            "tool_name": tool_name,
            "server_name": server_display_name,
            "html_content": html_content,
            "tool_result": raw_result,
            "server_id": server_id,
            "server_key": server_key,
            "server_source": server_source,
            "resource_uri": resource_uri,
            "tool_arguments": tool_arguments or {},
            "tool_input_schema": tool_input_schema or {"type": "object"},
        },
        meta=RegistryItemMeta(
            source=f"mcp_{source_label}",
            domain=CONTEXT_DOMAIN_MCP_APPS,
            tool_name=adapter_name,
        ),
    )

    # Short summary for LLM context — raw_result is already stored in the
    # registry payload (tool_result) and sent to the iframe via the MCP Apps
    # protocol (ui/notifications/tool-result).  Passing the full raw_result
    # here would cause the response LLM to include the raw JSON verbatim.
    summary = (
        f"[MCP App] Interactive widget rendered for tool '{tool_name}' "
        f"on server '{server_display_name}' (registry: {rid})"
    )

    return UnifiedToolOutput.data_success(
        message=summary,
        registry_updates={rid: registry_item},
        structured_data={
            CONTEXT_DOMAIN_MCP_APPS: [
                {
                    "tool_name": tool_name,
                    "server_name": server_display_name,
                    FIELD_REGISTRY_ID: rid,
                }
            ],
        },
    )
