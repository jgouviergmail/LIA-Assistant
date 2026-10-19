"""The MCP owner projects one stable owned page without private cached payloads."""

from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.user_mcp.projection import server_to_response
from src.domains.user_mcp.schemas import UserMCPServerResponse
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.personal_metadata_contract import (
    PersonalMCPReadItem,
    PersonalMCPToolItem,
)


def _public_server(original: UserMCPServerResponse, tools_offset: int) -> PersonalMCPReadItem:
    end = tools_offset + len(original.tools)
    values = original.model_dump(exclude={"url", "last_error", "tools", "shared_origin"})
    return PersonalMCPReadItem(
        **values,
        endpoint_host=urlsplit(original.url).hostname,
        has_connection_error=bool(original.last_error),
        tools=tuple(
            PersonalMCPToolItem.model_validate(tool.model_dump(exclude={"input_schema"}))
            for tool in original.tools
        ),
        next_tool_offset=end if end < original.tool_count else None,
    )


async def read_personal_mcp_metadata(
    db: AsyncSession,
    owner_id: UUID,
    *,
    server_id: UUID | None,
    offset: int,
    limit: int,
    tools_offset: int,
    tools_limit: int,
) -> tuple[tuple[PersonalMCPReadItem, ...], int]:
    service = UserMCPServerService(db)
    rows, total = await service.repository.get_page_for_user(
        owner_id, server_id=server_id, offset=offset, limit=limit
    )
    if server_id is not None and not total:
        raise ResourceNotFoundError("user_mcp_server", str(server_id))
    return (
        tuple(
            _public_server(
                server_to_response(
                    row,
                    service,
                    tools_offset=tools_offset,
                    tools_limit=tools_limit,
                    include_tool_schemas=False,
                ),
                tools_offset,
            )
            for row in rows
        ),
        total,
    )
