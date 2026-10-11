"""Only the original standalone server deletion can leave the personal MCP group."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.user_mcp.personal_state import _owned_row, _snapshot
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)


async def delete_personal_mcp_server(
    db: AsyncSession,
    owner_id: UUID,
    server_id: UUID,
    *,
    expected: PersonalMCPStateSnapshot,
    check: PersonalMCPWriteCheck,
) -> bool:
    row = await _owned_row(db, owner_id, server_id, lock=True)
    service = UserMCPServerService(db)
    if _snapshot(row, service) != expected:
        raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})
    await check(db)
    await service.delete_server(server_id, owner_id, before_write=check)
    return True
