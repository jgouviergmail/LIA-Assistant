"""Reuse original private CRUD schemas and URL/credential/quota rules in one owner."""

from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.user_mcp.personal_state import _owned_row, _snapshot
from src.domains.user_mcp.schemas import UserMCPServerCreate, UserMCPServerUpdate
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.personal_configuration_contract import PersonalMCPConfigurationResult
from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)

MCP_FORM_API_ONLY_FIELDS = frozenset({"hitl_required"})


def validate_configuration_fields(values: dict[str, JsonValue], *, creating: bool) -> None:
    """The private browser reuses original schemas; API-only controls stay excluded."""
    model = UserMCPServerCreate if creating else UserMCPServerUpdate
    if set(values) - (set(model.model_fields) - MCP_FORM_API_ONLY_FIELDS):
        raise ValueError("Unsupported private form fields")
    name = values.get("name")
    if "name" in values and (not isinstance(name, str) or not name.strip()):
        raise ValueError("A nonblank server name is required")


async def configure_personal_mcp_server(
    db: AsyncSession,
    owner_id: UUID,
    *,
    server_id: UUID | None,
    expected: PersonalMCPStateSnapshot | None,
    values: dict[str, JsonValue],
    read_check: PersonalMCPWriteCheck,
    write_check: PersonalMCPWriteCheck,
) -> PersonalMCPConfigurationResult:
    creating = server_id is None
    validate_configuration_fields(values, creating=creating)
    await read_check(db)
    service = UserMCPServerService(db)
    if creating != (expected is None) or (expected and expected.server.id != server_id):
        raise ValueError("Configuration target does not match its approved snapshot")
    if (
        server_id is not None
        and _snapshot(await _owned_row(db, owner_id, server_id), service) != expected
    ):
        raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})

    async def before_write(session: AsyncSession) -> None:
        await write_check(session)
        if (
            server_id is not None
            and _snapshot(await _owned_row(session, owner_id, server_id, lock=True), service)
            != expected
        ):
            raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})

    if creating:
        row = await service.create_server(
            owner_id, UserMCPServerCreate.model_validate(values), before_write=before_write
        )
    else:
        assert server_id is not None
        row = await service.update_server(
            server_id,
            owner_id,
            UserMCPServerUpdate.model_validate(values),
            before_write=before_write,
        )
    observed = _snapshot(row, service)
    return PersonalMCPConfigurationResult(
        server=observed.server, changed=expected is None or observed.digest != expected.digest
    )
