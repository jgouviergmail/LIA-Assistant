"""An owned full-row CAS delegates explicit state changes to the original service."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.agents.effects.digest import payload_digest
from src.domains.user_mcp.management_projection import _public_server
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.projection import server_to_response
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)


def _snapshot(row: UserMCPServer, service: UserMCPServerService) -> PersonalMCPStateSnapshot:
    return PersonalMCPStateSnapshot(
        server=_public_server(
            server_to_response(row, service, tools_limit=0, include_tool_schemas=False), 0
        ),
        digest=payload_digest(
            {column.key: getattr(row, column.key) for column in row.__table__.columns}
        ),
    )


async def _owned_row(
    db: AsyncSession, owner_id: UUID, server_id: UUID, *, lock: bool = False
) -> UserMCPServer:
    statement = (
        select(UserMCPServer)
        .where(UserMCPServer.id == server_id, UserMCPServer.user_id == owner_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    row = await db.scalar(statement)
    if row is None:
        raise ResourceNotFoundError("user_mcp_server", str(server_id))
    return row


async def observe_personal_mcp_state(
    db: AsyncSession, owner_id: UUID, server_id: UUID
) -> PersonalMCPStateSnapshot:
    return _snapshot(await _owned_row(db, owner_id, server_id), UserMCPServerService(db))


async def set_personal_mcp_state(
    db: AsyncSession,
    owner_id: UUID,
    server_id: UUID,
    enabled: bool,
    *,
    expected: PersonalMCPStateSnapshot,
    check: PersonalMCPWriteCheck,
) -> bool:
    row = await _owned_row(db, owner_id, server_id, lock=True)
    service = UserMCPServerService(db)
    if _snapshot(row, service) != expected:
        raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})
    await check(db)
    if row.is_enabled == enabled:
        return False
    await service.toggle_server(server_id, owner_id, enabled=enabled, before_write=check)
    return True
