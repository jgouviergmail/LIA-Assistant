"""
User MCP Server router with FastAPI endpoints.

Provides CRUD operations, toggle enable/disable, test connection,
and OAuth 2.1 authorization flow for per-user MCP servers.

Phase: evolution F2.1 — MCP Per-User
Created: 2026-02-28
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    MCP_USER_OAUTH_REDIRECT_PATH,
    MCP_USER_OAUTH_RESULT_DENIED,
    MCP_USER_OAUTH_RESULT_ERROR,
    MCP_USER_OAUTH_RESULT_PARAM,
    MCP_USER_OAUTH_STATE_REDIS_PREFIX,
)
from src.core.dependencies import get_db
from src.core.exceptions import ValidationError, raise_bad_gateway
from src.core.native_client import detect_native_client
from src.core.native_deep_link import NativeDeepLinkHost
from src.core.oauth.native_return import make_native_flow_probe, oauth_return_redirect
from src.core.session_dependencies import get_current_active_session
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServer, UserMCPServerStatus
from src.domains.user_mcp.schemas import (
    McpAppCallToolRequest,
    McpAppCallToolResponse,
    McpAppReadResourceRequest,
    McpAppReadResourceResponse,
    MCPDiscoveredToolResponse,
    UserMCPGenerateDescriptionResponse,
    UserMCPOAuthInitiateResponse,
    UserMCPServerCreate,
    UserMCPServerListResponse,
    UserMCPServerResponse,
    UserMCPServerUpdate,
    UserMCPTestConnectionResponse,
)
from src.domains.user_mcp.service import UserMCPServerService
from src.domains.users.models import User
from src.infrastructure.mcp.oauth_flow import MCPOAuthFlowHandler, safe_oauth_error_code_value
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _mcp_return(is_native: bool, params: dict[str, str]) -> RedirectResponse:
    """
    Close an MCP authorization on the surface that opened it.

    Args:
        is_native: Whether a native shell started the flow.
        params: Query the settings page reads — the same on both surfaces.

    Returns:
        A 302 to the app, or to the web settings page.
    """
    return oauth_return_redirect(
        is_native=is_native,
        host=NativeDeepLinkHost.MCP_CALLBACK,
        path=MCP_USER_OAUTH_REDIRECT_PATH,
        params=params,
    )


#: Did a native shell start this MCP authorization?
#:
#: MCP keeps its own state namespace, and reading the wrong one would answer
#: "not native" for every MCP flow — silently, and only in the shell.
mcp_return_is_native = make_native_flow_probe(MCP_USER_OAUTH_STATE_REDIS_PREFIX)


router = APIRouter(
    prefix="/mcp/servers",
    tags=["User MCP Servers"],
    # Administrable capability: a switched-off feature refuses at the
    # door, not only in the planner catalogue.
    dependencies=[
        *capability_dependencies(PlatformCapability.MCP),
        # A user-added MCP server can require OAuth, and that flow leaves for a
        # system browser like any other (ADR-246).
        Depends(detect_native_client),
    ],
)


def _server_to_response(
    server: UserMCPServer,
    service: UserMCPServerService,
) -> UserMCPServerResponse:
    """Convert UserMCPServer model to response schema."""
    # Parse discovered tools from cache
    tools: list[MCPDiscoveredToolResponse] = []
    if server.discovered_tools_cache:
        cache = server.discovered_tools_cache
        tool_list = cache if isinstance(cache, list) else cache.get("tools", [])
        tools = [
            MCPDiscoveredToolResponse(
                tool_name=t.get("name", t.get("tool_name", "")),
                description=t.get("description", ""),
                input_schema=t.get("input_schema", {}),
            )
            for t in tool_list
        ]

    # Delegate credential metadata extraction to service (no duplicate decrypt)
    metadata = service.build_response_metadata(server)

    return UserMCPServerResponse(
        id=server.id,
        name=server.name,
        url=server.url,
        auth_type=UserMCPAuthType(server.auth_type),
        status=UserMCPServerStatus(server.status),
        is_enabled=server.is_enabled,
        domain_description=server.domain_description,
        timeout_seconds=server.timeout_seconds,
        hitl_required=server.hitl_required,
        iterative_mode=server.iterative_mode,
        header_name=metadata["header_name"],
        has_credentials=metadata["has_credentials"],
        has_oauth_credentials=metadata["has_oauth_credentials"],
        oauth_scopes=metadata["oauth_scopes"],
        tool_count=len(tools),
        tools=tools,
        last_connected_at=server.last_connected_at,
        last_error=server.last_error,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


# =============================================================================
# List
# =============================================================================


@router.get(
    "",
    response_model=UserMCPServerListResponse,
    summary="List user MCP servers",
    description="Get all MCP servers for the current user.",
)
async def list_servers(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserMCPServerListResponse:
    """List all MCP servers for the current user."""
    service = UserMCPServerService(db)
    servers = await service.list_servers(user.id)

    logger.debug(
        "user_mcp_servers_listed",
        user_id=str(user.id),
        total=len(servers),
    )

    return UserMCPServerListResponse(
        servers=[_server_to_response(s, service) for s in servers],
        total=len(servers),
    )


# =============================================================================
# Create
# =============================================================================


@router.post(
    "",
    response_model=UserMCPServerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create MCP server",
    description="Register a new MCP server for the current user.",
)
async def create_server(
    data: UserMCPServerCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserMCPServerResponse:
    """Create a new user MCP server.

    ValidationError and ResourceNotFoundError (BaseAPIException subclasses)
    propagate automatically as HTTP 400/404 via FastAPI's exception handlers.
    """
    service = UserMCPServerService(db)
    server = await service.create_server(user.id, data)
    await db.commit()
    await db.refresh(server)
    return _server_to_response(server, service)


# =============================================================================
# Update
# =============================================================================


@router.patch(
    "/{server_id}",
    response_model=UserMCPServerResponse,
    summary="Update MCP server",
    description="Update an existing MCP server.",
)
async def update_server(
    server_id: UUID,
    data: UserMCPServerUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserMCPServerResponse:
    """Update an existing user MCP server.

    ResourceNotFoundError (404) and ValidationError (400) propagate automatically.
    """
    service = UserMCPServerService(db)
    server = await service.update_server(server_id, user.id, data)
    await db.commit()
    await db.refresh(server)
    return _server_to_response(server, service)


# =============================================================================
# Delete
# =============================================================================


@router.delete(
    "/{server_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete MCP server",
    description="Delete a user MCP server.",
)
async def delete_server(
    server_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a user MCP server.

    ResourceNotFoundError (404) propagates automatically.
    """
    service = UserMCPServerService(db)
    await service.delete_server(server_id, user.id)
    await db.commit()

    logger.info(
        "user_mcp_server_deleted_api",
        user_id=str(user.id),
        server_id=str(server_id),
    )


# =============================================================================
# Toggle
# =============================================================================


@router.patch(
    "/{server_id}/toggle",
    response_model=UserMCPServerResponse,
    summary="Toggle MCP server",
    description="Toggle enable/disable for an MCP server.",
)
async def toggle_server(
    server_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserMCPServerResponse:
    """Toggle enable/disable for a user MCP server.

    ResourceNotFoundError (404) propagates automatically.
    """
    service = UserMCPServerService(db)
    server = await service.toggle_server(server_id, user.id)
    await db.commit()
    await db.refresh(server)
    return _server_to_response(server, service)


# =============================================================================
# Test Connection
# =============================================================================


@router.post(
    "/{server_id}/test",
    response_model=UserMCPTestConnectionResponse,
    summary="Test MCP server connection",
    description="Test connection to an MCP server and discover available tools.",
)
async def test_connection(
    server_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserMCPTestConnectionResponse:
    """Test connection to a user MCP server and discover tools.

    ResourceNotFoundError (404) propagates automatically for ownership check.
    Pool/connection errors are returned in the response body (not as HTTP errors).
    """
    service = UserMCPServerService(db)
    result = await service.test_connection(server_id, user.id)
    await db.commit()

    tools = [
        MCPDiscoveredToolResponse(
            tool_name=t.get("name", t.get("tool_name", "")),
            description=t.get("description", ""),
            input_schema=t.get("input_schema", {}),
        )
        for t in result["tools"]
    ]

    return UserMCPTestConnectionResponse(
        success=result["success"],
        tool_count=result["tool_count"],
        tools=tools,
        error=result["error"],
        domain_description=result.get("domain_description"),
    )


# =============================================================================
# Generate Description
# =============================================================================


@router.post(
    "/{server_id}/generate-description",
    response_model=UserMCPGenerateDescriptionResponse,
    summary="Generate domain description",
    description="Force-(re)generate a domain description from discovered MCP tools.",
)
async def generate_description(
    server_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserMCPGenerateDescriptionResponse:
    """Force-generate domain description from cached MCP tools.

    Uses the tool cache from the last test_connection(). No network call.
    Overwrites any existing description.

    ValidationError (400) if no tools cache available.
    ResourceNotFoundError (404) for ownership check.
    """
    service = UserMCPServerService(db)
    result = await service.generate_description(server_id, user.id)
    await db.commit()

    return UserMCPGenerateDescriptionResponse(
        domain_description=result["domain_description"],
        tool_count=result["tool_count"],
    )


# =============================================================================
# OAuth Disconnect
# =============================================================================


@router.post(
    "/{server_id}/oauth/disconnect",
    response_model=UserMCPServerResponse,
    summary="Disconnect OAuth",
    description="Purge OAuth tokens to force re-authorization. Preserves client credentials.",
)
async def oauth_disconnect(
    server_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserMCPServerResponse:
    """Disconnect OAuth for a user MCP server.

    Clears access_token/refresh_token while preserving client_id/client_secret.
    Status reverts to 'auth_required' so the user can re-authorize.

    ResourceNotFoundError (404) and ValidationError (400) propagate automatically.
    """
    service = UserMCPServerService(db)
    server = await service.disconnect_oauth(server_id, user.id)
    await db.commit()
    await db.refresh(server)
    return _server_to_response(server, service)


# =============================================================================
# OAuth 2.1 Flow
# =============================================================================


@router.post(
    "/{server_id}/oauth/authorize",
    response_model=UserMCPOAuthInitiateResponse,
    summary="Start OAuth authorization",
    description="Initiate OAuth 2.1 authorization flow for an MCP server.",
)
async def oauth_authorize(
    server_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserMCPOAuthInitiateResponse:
    """Initiate OAuth 2.1 authorization flow for a user MCP server.

    ResourceNotFoundError (404) propagates automatically for ownership check.
    """
    service = UserMCPServerService(db)
    server = await service.get_with_ownership_check(server_id, user.id)

    if server.auth_type != UserMCPAuthType.OAUTH2.value:
        raise ValidationError("Server auth_type must be 'oauth2' to use OAuth authorization")

    # Extract pre-registered client credentials if available
    client_id: str | None = None
    client_secret: str | None = None
    stored_issuer: str | None = None
    creds = service.get_decrypted_credentials(server)
    if creds:
        client_id = creds.get("client_id")
        client_secret = creds.get("client_secret")
        stored_issuer = creds.get("issuer")

    # Extract user-specified scopes (stored in oauth_metadata by service)
    requested_scopes = (server.oauth_metadata or {}).get("requested_scopes", "")

    async with MCPOAuthFlowHandler() as handler:
        try:
            authorization_url, metadata_cache = await handler.initiate_flow(
                server_id=server.id,
                user_id=user.id,
                mcp_url=server.url,
                cached_metadata=server.oauth_metadata,
                client_id=client_id,
                client_secret=client_secret,
                requested_scopes=requested_scopes,
                stored_issuer=stored_issuer,
            )
        except Exception as e:
            logger.error(
                "user_mcp_oauth_initiate_failed",
                user_id=str(user.id),
                server_id=str(server_id),
                error=str(e),
            )
            raise_bad_gateway(
                "Failed to initiate OAuth flow. The MCP server may be unreachable "
                "or misconfigured.",
                server_id=str(server_id),
            )

    # Cache OAuth metadata for future flows (avoids re-discovery)
    if metadata_cache:
        await service.cache_oauth_metadata(server, metadata_cache)
        await db.commit()

    return UserMCPOAuthInitiateResponse(authorization_url=authorization_url)


# =============================================================================
# MCP Apps Proxy (evolution F2.5 — interactive widgets)
# =============================================================================


@router.post(
    "/{server_id}/app/call-tool",
    response_model=McpAppCallToolResponse,
    summary="Proxy tool call from MCP App",
    description="Proxy a tool call from an MCP App iframe to the user's MCP server.",
)
async def app_proxy_call_tool(
    server_id: UUID,
    request: McpAppCallToolRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> McpAppCallToolResponse:
    """Proxy a tool call from an MCP App iframe to the user's MCP server."""
    from src.infrastructure.mcp.user_pool import get_user_mcp_pool

    service = UserMCPServerService(db)
    await service.get_with_ownership_check(server_id, user.id)

    pool = get_user_mcp_pool()
    if pool is None:
        return McpAppCallToolResponse(success=False, error="MCP pool not available")

    try:
        result = await pool.call_tool(
            user_id=user.id,
            server_id=server_id,
            tool_name=request.tool_name,
            arguments=request.arguments,
        )
        return McpAppCallToolResponse(success=True, result=result)
    except Exception as e:
        logger.warning(
            "mcp_app_proxy_call_tool_failed",
            server_id=str(server_id),
            tool_name=request.tool_name,
            error=str(e),
        )
        return McpAppCallToolResponse(success=False, error=f"Tool call failed: {type(e).__name__}")


@router.post(
    "/{server_id}/app/read-resource",
    response_model=McpAppReadResourceResponse,
    summary="Proxy resource read from MCP App",
    description="Proxy a resource read from an MCP App iframe to the user's MCP server.",
)
async def app_proxy_read_resource(
    server_id: UUID,
    request: McpAppReadResourceRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> McpAppReadResourceResponse:
    """Proxy a resource read from an MCP App iframe to the user's MCP server."""
    from src.infrastructure.mcp.user_pool import get_user_mcp_pool

    service = UserMCPServerService(db)
    await service.get_with_ownership_check(server_id, user.id)

    pool = get_user_mcp_pool()
    if pool is None:
        return McpAppReadResourceResponse(success=False, error="MCP pool not available")

    try:
        content = await pool.read_resource(
            user_id=user.id,
            server_id=server_id,
            uri=request.uri,
        )
        if content is None:
            return McpAppReadResourceResponse(
                success=False, error="Resource not found or unreadable"
            )
        return McpAppReadResourceResponse(success=True, content=content, mime_type="text/html")
    except Exception as e:
        logger.warning(
            "mcp_app_proxy_read_resource_failed",
            server_id=str(server_id),
            uri=request.uri,
            error=str(e),
        )
        return McpAppReadResourceResponse(
            success=False, error=f"Resource read failed: {type(e).__name__}"
        )


@router.get(
    "/oauth/callback",
    summary="OAuth callback",
    description="Handle OAuth 2.1 callback from authorization server.",
    include_in_schema=False,  # Hidden from docs (internal redirect)
)
async def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    iss: str | None = None,
    error: str | None = None,
    is_native: bool = Depends(mcp_return_is_native),
) -> RedirectResponse:
    """
    Handle OAuth 2.1 callback.

    Security Model: No session auth required (user is mid-redirect).
    User identity comes from the signed state parameter stored in Redis.
    State is single-use (deleted after consumption) to prevent replay attacks.
    The ``iss`` parameter, when sent by the authorization server, is validated
    against the recorded issuer before the code is redeemed (RFC 9207).

    Every parameter is optional at the FastAPI layer: this endpoint is a
    browser redirect target, so a denial or malformed response must land the
    user back on the frontend with a marker — never on a bare 422.
    """
    if error or not code or not state:
        # `error` is provider-controlled free text: log only an allowlisted
        # code (SEC-030) and never reflect the raw value into the redirect.
        logger.warning(
            "user_mcp_oauth_callback_rejected",
            oauth_error=safe_oauth_error_code_value(error),
            has_code=bool(code),
            has_state=bool(state),
        )
        denied = error == "access_denied"
        params = (
            {MCP_USER_OAUTH_RESULT_PARAM: MCP_USER_OAUTH_RESULT_DENIED}
            if denied
            else {
                MCP_USER_OAUTH_RESULT_PARAM: MCP_USER_OAUTH_RESULT_ERROR,
                "error": "oauth_failed",
            }
        )
        return _mcp_return(is_native, params)

    async with MCPOAuthFlowHandler() as handler:
        try:
            server_id, user_id, encrypted_creds = await handler.handle_callback(
                code=code, state=state, iss=iss
            )

            # Persist encrypted tokens and mark server as active
            await UserMCPServerService.update_oauth_credentials(server_id, encrypted_creds)

            logger.info(
                "user_mcp_oauth_callback_success",
                server_id=str(server_id),
                user_id=str(user_id),
            )

            return _mcp_return(is_native, {"mcp_oauth": "success", "server_id": str(server_id)})

        except Exception as e:
            logger.error(
                "user_mcp_oauth_callback_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

            return _mcp_return(
                is_native,
                {
                    MCP_USER_OAUTH_RESULT_PARAM: MCP_USER_OAUTH_RESULT_ERROR,
                    "error": "oauth_failed",
                },
            )
