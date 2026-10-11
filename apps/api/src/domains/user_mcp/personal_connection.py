"""Release transactions during discovery; freshly guard both success/error writes."""

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError, ValidationError
from src.domains.user_mcp.personal_state import _owned_row, _snapshot
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.personal_connection_contract import PersonalMCPConnectionResult
from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)
from src.infrastructure.mcp.security import validate_http_endpoint


async def test_personal_mcp_connection(
    db: AsyncSession,
    owner_id: UUID,
    server_id: UUID,
    *,
    expected: PersonalMCPStateSnapshot,
    read_check: PersonalMCPWriteCheck,
    write_check: PersonalMCPWriteCheck,
) -> PersonalMCPConnectionResult:
    service = UserMCPServerService(db)

    async def before_connect(session: AsyncSession) -> None:
        await read_check(session)
        row = await _owned_row(session, owner_id, server_id)
        if _snapshot(row, service) != expected:
            raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})
        valid, _ = await validate_http_endpoint(row.url)
        if not valid:
            raise ValidationError("MCP endpoint unavailable under the original URL policy")
        await read_check(session)
        if _snapshot(await _owned_row(session, owner_id, server_id), service) != expected:
            raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})
        await session.commit()

    async def before_write(session: AsyncSession) -> None:
        await write_check(session)
        if (
            _snapshot(await _owned_row(session, owner_id, server_id, lock=True), service)
            != expected
        ):
            raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})

    try:
        result = await service.test_connection(
            server_id,
            owner_id,
            before_connect=before_connect,
            before_write=before_write,
        )
        if result.get("error") == "MCP user pool not initialized":
            raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
        current = _snapshot(await _owned_row(db, owner_id, server_id), service).server
        return PersonalMCPConnectionResult(
            success=result["success"],
            server=current,
            error=None if result["success"] else "connection_failed",
        )
    except Exception, asyncio.CancelledError:
        await service._disconnect_from_pool(owner_id, server_id)
        raise
