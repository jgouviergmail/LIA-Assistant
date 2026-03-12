"""
Admin MCP Servers API — List and toggle admin-configured MCP servers.

Admin MCP servers are configured globally in MCP_SERVERS_CONFIG (.env).
Users can toggle individual servers on/off via their admin_mcp_disabled_servers list.

Phase: evolution F2.5 — Admin MCP Per-Server Routing & User Toggle
Created: 2026-03-03
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.user_mcp.schemas import (
    AdminMCPServerResponse,
    AdminMCPToggleResponse,
    AdminMCPToolInfo,
    McpAppCallToolRequest,
    McpAppCallToolResponse,
    McpAppReadResourceRequest,
    McpAppReadResourceResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/mcp/admin-servers", tags=["mcp-admin"])


def _humanize_server_key(key: str) -> str:
    """Convert a server key to a human-readable display name.

    Examples:
        "google_flights" → "Google Flights"
        "huggingface_hub" → "Huggingface Hub"
    """
    return key.replace("_", " ").title()


@router.get(
    "",
    response_model=list[AdminMCPServerResponse],
    summary="List admin MCP servers",
    description="List all admin-configured MCP servers with tools and per-user toggle status.",
)
async def list_admin_servers(
    user: User = Depends(get_current_active_session),
) -> list[AdminMCPServerResponse]:
    """List all admin MCP servers with their tools and user enable/disable status."""
    from src.infrastructure.mcp.client_manager import get_mcp_client_manager
    from src.infrastructure.mcp.registration import get_admin_mcp_domains

    manager = get_mcp_client_manager()
    if not manager:
        return []

    disabled_servers: list[str] = getattr(user, "admin_mcp_disabled_servers", None) or []
    disabled_set = set(disabled_servers)
    admin_domains = get_admin_mcp_domains()
    discovered = manager.discovered_tools

    from src.domains.agents.registry.domain_taxonomy import slugify_mcp_server_name

    result: list[AdminMCPServerResponse] = []
    for server_key, tools in discovered.items():
        # Description from domain store (populated at startup by registration.py)
        domain_slug = slugify_mcp_server_name(server_key)
        description = admin_domains.get(domain_slug)

        tool_infos = [AdminMCPToolInfo(name=t.tool_name, description=t.description) for t in tools]

        result.append(
            AdminMCPServerResponse(
                server_key=server_key,
                name=_humanize_server_key(server_key),
                description=description,
                tools_count=len(tools),
                tools=tool_infos,
                enabled_for_user=server_key not in disabled_set,
            )
        )

    return result


@router.patch(
    "/{server_key}/toggle",
    response_model=AdminMCPToggleResponse,
    summary="Toggle admin MCP server",
    description="Toggle enable/disable for an admin MCP server for the current user.",
)
async def toggle_admin_server(
    server_key: str,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> AdminMCPToggleResponse:
    """Toggle an admin MCP server on/off for the current user.

    Adds or removes the server_key from user.admin_mcp_disabled_servers.
    """
    from src.infrastructure.mcp.client_manager import get_mcp_client_manager

    # Validate server_key exists
    manager = get_mcp_client_manager()
    if not manager or server_key not in manager.discovered_tools:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin MCP server '{server_key}' not found",
        )

    disabled_servers: list[str] = list(getattr(user, "admin_mcp_disabled_servers", None) or [])

    if server_key in disabled_servers:
        # Re-enable: remove from disabled list
        disabled_servers.remove(server_key)
        enabled_for_user = True
    else:
        # Disable: add to disabled list
        disabled_servers.append(server_key)
        enabled_for_user = False

    user.admin_mcp_disabled_servers = disabled_servers
    db.add(user)
    await db.commit()

    logger.info(
        "admin_mcp_server_toggled",
        server_key=server_key,
        user_id=str(user.id),
        enabled=enabled_for_user,
    )

    return AdminMCPToggleResponse(
        server_key=server_key,
        enabled_for_user=enabled_for_user,
    )


# =============================================================================
# MCP Apps Proxy (evolution F2.5 — interactive widgets)
# =============================================================================


@router.post(
    "/{server_key}/app/call-tool",
    response_model=McpAppCallToolResponse,
    summary="Proxy tool call from MCP App (admin)",
    description="Proxy a tool call from an MCP App iframe to an admin MCP server.",
)
async def admin_app_proxy_call_tool(
    server_key: str,
    request: McpAppCallToolRequest,
    user: User = Depends(get_current_active_session),
) -> McpAppCallToolResponse:
    """Proxy a tool call from an MCP App iframe to an admin MCP server."""
    from src.infrastructure.mcp.client_manager import get_mcp_client_manager

    manager = get_mcp_client_manager()
    if not manager or server_key not in manager.discovered_tools:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin MCP server '{server_key}' not found",
        )

    try:
        result = await manager.call_tool(
            server_name=server_key,
            tool_name=request.tool_name,
            arguments=request.arguments,
        )
        return McpAppCallToolResponse(success=True, result=result)
    except Exception as e:
        logger.warning(
            "admin_mcp_app_proxy_call_tool_failed",
            server_key=server_key,
            tool_name=request.tool_name,
            error=str(e),
        )
        return McpAppCallToolResponse(success=False, error=f"Tool call failed: {type(e).__name__}")


@router.post(
    "/{server_key}/app/read-resource",
    response_model=McpAppReadResourceResponse,
    summary="Proxy resource read from MCP App (admin)",
    description="Proxy a resource read from an MCP App iframe to an admin MCP server.",
)
async def admin_app_proxy_read_resource(
    server_key: str,
    request: McpAppReadResourceRequest,
    user: User = Depends(get_current_active_session),
) -> McpAppReadResourceResponse:
    """Proxy a resource read from an MCP App iframe to an admin MCP server."""
    from src.infrastructure.mcp.client_manager import get_mcp_client_manager

    manager = get_mcp_client_manager()
    if not manager or server_key not in manager.discovered_tools:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin MCP server '{server_key}' not found",
        )

    try:
        content = await manager.read_resource(
            server_name=server_key,
            uri=request.uri,
        )
        if content is None:
            return McpAppReadResourceResponse(
                success=False, error="Resource not found or unreadable"
            )
        return McpAppReadResourceResponse(success=True, content=content, mime_type="text/html")
    except Exception as e:
        logger.warning(
            "admin_mcp_app_proxy_read_resource_failed",
            server_key=server_key,
            uri=request.uri,
            error=str(e),
        )
        return McpAppReadResourceResponse(
            success=False, error=f"Resource read failed: {type(e).__name__}"
        )
