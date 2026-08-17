"""
MCP Shared Utilities.

Provides helpers shared by both admin and user MCP subsystems:
- ``extract_app_meta``: Extract MCP Apps metadata from SDK Tool objects.
- ``is_app_only``: Check if a tool is iframe-only (not exposed to LLM).
- ``build_mcp_app_output``: Build a UnifiedToolOutput for MCP Apps (interactive widgets).
- ``unwrap_exception_group`` / ``is_modern_only_rejection`` /
  ``MCPModernOnlyServerError``: root-cause surfacing for anyio-wrapped
  transport failures and protocol-revision rejections (ADR-224).
- ``build_client_info``: LIA's ``clientInfo`` identity for the MCP handshake.

Phase: evolution F2.5 — MCP Apps
Created: 2026-03-04
"""

from __future__ import annotations

import time
from typing import Any

import httpx2
from mcp.shared.exceptions import MCPError
from mcp.types import Implementation

from src.core.config import settings
from src.core.constants import (
    MCP_CLIENT_INFO_NAME,
    MCP_ERROR_UNSUPPORTED_PROTOCOL_VERSION,
)
from src.core.field_names import FIELD_REGISTRY_ID
from src.domains.agents.constants import CONTEXT_DOMAIN_MCP_APPS
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.tools.output import UnifiedToolOutput


class MCPModernOnlyServerError(RuntimeError):
    """The MCP server rejected every protocol revision this client speaks.

    LIA's dual-era client speaks revision 2026-07-28 AND falls back to the
    legacy ``initialize`` handshake; a rejection therefore means the server
    only accepts revisions outside that range. The message is deliberately
    self-contained: this diagnostic is the only signal the user ever sees
    (spec 2026-07-28, Versioning & Compatibility).
    """

    def __init__(self) -> None:
        super().__init__(
            "This MCP server rejected every protocol revision this LIA "
            "version speaks (2026-07-28 and the legacy handshake down to "
            "2024-11-05). The server likely requires a newer MCP revision — "
            "check the server's documentation or update LIA."
        )


def unwrap_exception_group(exc: BaseException) -> BaseException:
    """Recursively unwrap single-child ``ExceptionGroup`` nesting.

    The MCP SDK's transports run inside anyio TaskGroups: a failure gets
    wrapped in one ``ExceptionGroup`` per nesting level, and ``str(exc)``
    then reads "unhandled errors in a TaskGroup" — hiding the root cause.
    Groups with several children are returned as-is (no arbitration).

    Args:
        exc: Any exception, possibly nested in ExceptionGroups.

    Returns:
        The innermost single cause, or ``exc`` unchanged.
    """
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


def is_modern_only_rejection(exc: BaseException) -> bool:
    """Whether an exception is a modern-only server rejecting a legacy client.

    Two rejection shapes exist on the wire (spec 2026-07-28, compatibility
    matrix):

    - Streamable HTTP: the request is rejected with ``400 Bad Request``
      (missing/unacceptable protocol headers) — the SDK surfaces
      ``httpx2.HTTPStatusError``.
    - A server that parses JSON-RPC answers
      ``UnsupportedProtocolVersionError`` (``-32022``).

    Args:
        exc: The root-cause exception (already unwrapped).

    Returns:
        True when the failure identifies a protocol-revision rejection.
    """
    if isinstance(exc, httpx2.HTTPStatusError):
        return exc.response.status_code == 400
    if isinstance(exc, MCPError):
        # bool(): the SDK's ErrorData.code resolves as Any under MyPy strict.
        return bool(exc.code == MCP_ERROR_UNSUPPORTED_PROTOCOL_VERSION)
    return False


def build_client_info() -> Implementation:
    """MCP ``clientInfo`` identifying LIA in the handshake (spec SHOULD).

    Returns:
        Implementation with the LIA client name and the running app version.
    """
    return Implementation(name=MCP_CLIENT_INFO_NAME, version=settings.app_version)


def drop_none_values(arguments: dict[str, Any]) -> dict[str, Any]:
    """Drop top-level keys whose value is ``None`` from MCP tool arguments.

    Optional MCP parameters left unset are materialised as ``None`` by the
    Pydantic args schema (``Field(default=None)``). Forwarding them verbatim
    makes strictly-typed MCP servers (e.g. Go-based) reject the call with
    ``parameter X is not of type string, is <nil>``. Per the MCP/JSON-RPC
    convention an unset optional must be omitted, not sent as ``null``.

    Only ``None`` is removed — falsy-but-valid values (``False``, ``0``, ``""``,
    ``[]``) are preserved. Non-recursive by design: nested objects pass as-is.

    Args:
        arguments: Tool arguments mapping (keyword args from the LLM/schema).

    Returns:
        A new dict without ``None``-valued keys.
    """
    return {key: value for key, value in arguments.items() if value is not None}


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
