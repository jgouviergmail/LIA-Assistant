"""Owned exact-row CAS reuses the original token purge and pool invalidation."""

from uuid import UUID

from pydantic import JsonValue, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ValidationError
from src.core.security.utils import decrypt_data
from src.domains.user_mcp.personal_state import _owned_row, _snapshot
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)


async def disconnect_personal_mcp_oauth(
    db: AsyncSession,
    owner_id: UUID,
    server_id: UUID,
    *,
    expected: PersonalMCPStateSnapshot,
    check: PersonalMCPWriteCheck,
) -> bool:
    service = UserMCPServerService(db)
    row = await _owned_row(db, owner_id, server_id, lock=True)
    if _snapshot(row, service) != expected:
        raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})
    if row.auth_type != "oauth2":
        raise ValidationError("Only OAuth personal MCP servers can be disconnected")
    if row.credentials_encrypted:
        try:
            TypeAdapter(dict[str, JsonValue]).validate_json(decrypt_data(row.credentials_encrypted))
        except ValueError:
            raise ValidationError(
                "Stored authentication cannot be read; restore it in settings"
            ) from None
    await check(db)
    await service.disconnect_oauth(server_id, owner_id, before_write=check)
    return True
