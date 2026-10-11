"""One approved originating browser submits secrets; only public receipts persist."""

from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_status import (
    ApplicationCommandStatus,
    read_command_status,
)
from src.domains.agents.application.continuation_approval import claim_approved_waiting_interaction
from src.domains.agents.application.export_download_service import _download_failure
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.personal_mcp_configuration import (
    authorize_personal_mcp_configuration,
)
from src.domains.agents.application.personal_mcp_configuration_schemas import (
    PersonalMCPConfigurationPatch,
    canonical_personal_mcp_configuration,
)
from src.domains.agents.application.personal_mcp_execution import (
    check_personal_mcp_write,
    commit_personal_mcp_change,
    lock_personal_mcp_write,
)
from src.domains.agents.application.secure_continuation import (
    finish_application_continuation,
    note_continuation_claim,
)
from src.domains.agents.application.state_changes import publish_preference_change
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.mcp.personal_state_contract import PersonalMCPWriteCheck
from src.infrastructure.mcp.personal_state_gateway import get_personal_mcp_state


async def serve_personal_mcp_configuration(
    db: AsyncSession,
    actor_id: UUID,
    command_id: UUID,
    values: dict[str, JsonValue],
    origin: ApplicationOrigin | None,
) -> ApplicationCommandStatus:
    status = await read_command_status(db, actor_id, command_id, origin)
    if (
        status.operation_id != "personal_mcp.configuration"
        or status.phase != ApplicationPhase.WAITING
    ):
        raise AuthorizationError(detail={"error_code": "INVALID_INPUT"})
    ticket = await claim_approved_waiting_interaction(db, actor_id, command_id, origin)
    if ticket is None:
        raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})
    receipt = PreferenceWriteReceipt()
    draft = ticket.command.draft

    async def read_check(session: AsyncSession) -> None:
        await check_personal_mcp_write(session, actor_id, draft)
        await authorize_personal_mcp_configuration(session, actor_id, origin)

    async def write_check(session: AsyncSession) -> None:
        await lock_personal_mcp_write(session, actor_id, draft)
        await authorize_personal_mcp_configuration(session, actor_id, origin)

    try:
        await note_continuation_claim(db, ticket)
        if not canonical_personal_mcp_configuration(draft):
            raise ValueError("Configuration requires its exact approved target")
        selected = PersonalMCPConfigurationPatch.model_validate(
            draft.intent
        ).personal_mcp_configuration
        writer = get_personal_mcp_state().configure
        if writer is None:
            raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
        result = await writer(
            db,
            actor_id,
            server_id=selected.request.server_id,
            expected=selected.expected,
            values=values,
            read_check=read_check,
            write_check=write_check,
        )
        await read_check(db)
        server = result.server
        observed: dict[str, JsonValue] = {
            "personal_mcp_configuration": {
                "server_id": str(server.id),
                "name": server.name,
                "endpoint_host": server.endpoint_host,
                "auth_type": server.auth_type,
                "status": server.status,
                "has_credentials": server.has_credentials,
                "has_oauth_credentials": server.has_oauth_credentials,
                "configuration_saved": True,
                "connection_verified": False,
            }
        }

        async def saved(check: PersonalMCPWriteCheck) -> bool:
            await check(db)
            await read_check(db)
            return result.changed

        await commit_personal_mcp_change(
            db, actor_id, draft, receipt, saved, committed_values=observed
        )
        outcome = ApplicationExecutionOutcome(
            success=True,
            phase=ApplicationPhase.COMMITTED,
            committed=True,
            no_op=receipt.no_op,
            values=observed,
        )
    except BaseException as error:
        await db.rollback()
        failed = _download_failure(error, receipt).model_copy(
            update={"values": receipt.values or {}}
        )
        await finish_application_continuation(ticket, failed)
        publish_preference_change(draft, receipt)
        raise
    await finish_application_continuation(ticket, outcome)
    publish_preference_change(draft, receipt)
    await read_check(db)
    return await read_command_status(db, actor_id, command_id, origin)
