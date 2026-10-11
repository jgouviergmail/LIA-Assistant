"""Original MCP validation/update owns non-secret edits under the same full-row CAS."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.user_mcp.personal_state import _owned_row, _snapshot
from src.domains.user_mcp.schemas import UserMCPServerUpdate
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.personal_settings_contract import PersonalMCPSettingsValues
from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)


async def update_personal_mcp_settings(
    db: AsyncSession,
    owner_id: UUID,
    server_id: UUID,
    patch: PersonalMCPSettingsValues,
    *,
    expected: PersonalMCPStateSnapshot,
    check: PersonalMCPWriteCheck,
) -> bool:
    desired = PersonalMCPSettingsValues.model_validate(patch.model_dump(exclude_unset=True))
    row = await _owned_row(db, owner_id, server_id, lock=True)
    service = UserMCPServerService(db)
    if _snapshot(row, service) != expected:
        raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})
    await check(db)
    values = desired.model_dump(exclude_unset=True)
    if all(getattr(row, field) == value for field, value in values.items()):
        return False
    await service.update_server(
        server_id, owner_id, UserMCPServerUpdate.model_validate(values), before_write=check
    )
    return True
