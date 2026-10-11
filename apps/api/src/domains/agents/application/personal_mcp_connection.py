"""One original HITL protects discovery; receipts report only observed stored values."""

from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_connection_schemas import (
    PersonalMCPConnectionInput,
    PersonalMCPConnectionObservation,
    PersonalMCPConnectionPatch,
    canonical_personal_mcp_connection,
    connection_after,
    connection_before,
)
from src.domains.agents.application.personal_mcp_connection_spec import (
    PERSONAL_MCP_CONNECTION_OPERATION,
)
from src.domains.agents.application.personal_mcp_execution import (
    check_personal_mcp_write,
    commit_personal_mcp_change,
    lock_personal_mcp_write,
)
from src.domains.agents.application.personal_mcp_read import require_personal_mcp_access
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.mcp.personal_state_contract import PersonalMCPWriteCheck
from src.infrastructure.mcp.personal_state_gateway import get_personal_mcp_state


async def prepare_personal_mcp_connection(
    db: AsyncSession,
    actor_id: UUID,
    request: PersonalMCPConnectionInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = PersonalMCPConnectionInput.model_validate(request.model_dump())
    await require_personal_mcp_access(db, actor_id)
    gateway = get_personal_mcp_state()
    if gateway.connect is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    expected = await gateway.read(db, actor_id, desired.server_id)
    await require_personal_mcp_access(db, actor_id)
    if len(expected.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("MCP probe preview too large")
    return build_action_content(
        actor_id,
        PERSONAL_MCP_CONNECTION_OPERATION,
        PersonalMCPConnectionPatch(
            personal_mcp_connection=PersonalMCPConnectionObservation(
                request=desired, expected=expected
            )
        ),
        {"personal_mcp_connection": connection_before(expected)},
        {"personal_mcp_connection": connection_after(expected)},
        command_id=command_id,
    )


async def execute_personal_mcp_connection(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if (
        draft.actor_id != actor_id
        or draft.operation_id != PERSONAL_MCP_CONNECTION_OPERATION.operation_id
    ):
        raise CommandRejected("FORBIDDEN")
    if not canonical_personal_mcp_connection(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = PersonalMCPConnectionPatch.model_validate(draft.intent).personal_mcp_connection
    writer = get_personal_mcp_state().connect
    if writer is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})

    async def read_check(session: AsyncSession) -> None:
        await check_personal_mcp_write(session, actor_id, draft)

    async def write_check(session: AsyncSession) -> None:
        await lock_personal_mcp_write(session, actor_id, draft)

    result = await writer(
        db,
        actor_id,
        selected.request.server_id,
        expected=selected.expected,
        read_check=read_check,
        write_check=write_check,
    )

    async def saved(check: PersonalMCPWriteCheck) -> bool:
        await check(db)
        return True

    server = result.server
    observed: dict[str, JsonValue] = {
        "personal_mcp_connection": {
            "server_id": str(server.id),
            "connection_success": result.success,
            "status": server.status,
            "tool_count": server.tool_count,
            "domain_description": server.domain_description,
            "last_connected_at": (
                server.last_connected_at.isoformat() if server.last_connected_at else None
            ),
            "error_kind": result.error,
        }
    }
    await commit_personal_mcp_change(db, actor_id, draft, receipt, saved, committed_values=observed)
