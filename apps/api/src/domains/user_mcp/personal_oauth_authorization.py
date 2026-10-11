"""Exact owned OAuth row transitions share original initiation and persistence."""

from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ValidationError
from src.domains.user_mcp.authorization import initiate_personal_mcp_authorization
from src.domains.user_mcp.personal_state import _owned_row, _snapshot
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.oauth_application_guard import MCPApplicationOAuthCheck
from src.infrastructure.mcp.personal_oauth_contract import PersonalMCPOAuthStart
from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)


async def start_personal_mcp_oauth(
    db: AsyncSession,
    user_id: UUID,
    server_id: UUID,
    *,
    application_command_id: UUID,
    application_check: MCPApplicationOAuthCheck,
) -> PersonalMCPOAuthStart:
    metadata: dict[str, JsonValue] = {}

    async def capture(value: dict[str, JsonValue]) -> None:
        metadata.update(value)

    response = await initiate_personal_mcp_authorization(
        db,
        user_id,
        server_id,
        application_command_id=application_command_id,
        application_check=application_check,
        metadata_sink=capture,
    )
    return PersonalMCPOAuthStart(authorization_url=response.authorization_url, metadata=metadata)


async def save_personal_mcp_oauth(
    db: AsyncSession,
    owner_id: UUID,
    server_id: UUID,
    encrypted_credentials: str,
    metadata: dict[str, JsonValue],
    *,
    expected: PersonalMCPStateSnapshot,
    check: PersonalMCPWriteCheck,
) -> bool:
    service = UserMCPServerService(db)
    row = await _owned_row(db, owner_id, server_id, lock=True)
    if _snapshot(row, service) != expected:
        raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})
    if row.auth_type != "oauth2":
        raise ValidationError("Only OAuth personal MCP servers can be authorized")
    await check(db)
    await service._disconnect_from_pool(owner_id, server_id, strict=True)
    await check(db)
    await service.set_owned_oauth_credentials(
        server_id, owner_id, encrypted_credentials, before_write=check
    )
    await service.cache_oauth_metadata(row, metadata)
    return True
