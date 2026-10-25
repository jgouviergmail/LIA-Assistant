"""One original UI metadata projection for HTTP and native personal management."""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.capability_origin import CapabilityOrigin, CapabilityShare
from src.domains.shared.capability_origins import capability_origins
from src.domains.shared.capability_shares import capability_shares
from src.domains.user_mcp.models import (
    UserMCPAuthType,
    UserMCPServer,
    UserMCPServerStatus,
)
from src.domains.user_mcp.schemas import (
    MCPDiscoveredToolResponse,
    UserMCPServerResponse,
)

if TYPE_CHECKING:
    from src.domains.user_mcp.service import UserMCPServerService


def server_to_response(
    server: UserMCPServer,
    service: UserMCPServerService,
    *,
    tools_offset: int = 0,
    tools_limit: int | None = None,
    include_tool_schemas: bool = True,
    shared_origin: CapabilityOrigin | None = None,
    shared_with: Sequence[CapabilityShare] = (),
) -> UserMCPServerResponse:
    tools: list[MCPDiscoveredToolResponse] = []
    tool_count = 0
    if server.discovered_tools_cache:
        cache = server.discovered_tools_cache
        tool_list = cache if isinstance(cache, list) else cache.get("tools", [])
        tool_count = len(tool_list)
        end = tools_offset + tools_limit if tools_limit is not None else None
        tools = [
            MCPDiscoveredToolResponse(
                tool_name=t.get("name", t.get("tool_name", "")),
                description=t.get("description", ""),
                input_schema=t.get("input_schema", {}) if include_tool_schemas else {},
                title=t.get("title"),
            )
            for t in tool_list[tools_offset:end]
        ]
    metadata = service.build_response_metadata(server)
    return UserMCPServerResponse(
        shared_origin=shared_origin,
        shared_with=list(shared_with),
        id=server.id,
        name=server.name,
        url=server.url,
        auth_type=UserMCPAuthType(server.auth_type),
        status=UserMCPServerStatus(server.status),
        is_enabled=server.is_enabled,
        plugin_id=server.plugin_id,
        domain_description=server.domain_description,
        timeout_seconds=server.timeout_seconds,
        hitl_required=server.hitl_required,
        iterative_mode=server.iterative_mode,
        header_name=metadata["header_name"],
        has_credentials=metadata["has_credentials"],
        has_oauth_credentials=metadata["has_oauth_credentials"],
        oauth_scopes=metadata["oauth_scopes"],
        tool_count=tool_count,
        tools=tools,
        last_connected_at=server.last_connected_at,
        last_error=server.last_error,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


async def owned_server_response(
    db: AsyncSession, server: UserMCPServer, service: UserMCPServerService
) -> UserMCPServerResponse:
    origins = await capability_origins(db, server.user_id, "mcp", [server.id])
    shares = await capability_shares(db, server.user_id, "mcp", [server.id])
    return server_to_response(
        server,
        service,
        shared_origin=origins.get(server.id),
        shared_with=shares.get(server.id, ()),
    )
