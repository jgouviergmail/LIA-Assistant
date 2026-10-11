"""Reuse original accounted generation without retaining a row lock during billing."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.user_mcp.personal_state import _owned_row, _snapshot
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.personal_description_contract import PersonalMCPDescriptionResult
from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)


async def regenerate_personal_mcp_description(
    db: AsyncSession,
    owner_id: UUID,
    server_id: UUID,
    *,
    expected: PersonalMCPStateSnapshot,
    read_check: PersonalMCPWriteCheck,
    write_check: PersonalMCPWriteCheck,
) -> PersonalMCPDescriptionResult:
    service = UserMCPServerService(db)

    async def before_generate(session: AsyncSession) -> None:
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

    result = await service.generate_description(
        server_id, owner_id, before_generate=before_generate, before_write=before_write
    )
    return PersonalMCPDescriptionResult.model_validate(result)
