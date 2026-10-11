"""Once-approved OAuth initiation and final save require the original live browser."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue
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
from src.domains.agents.application.personal_mcp_execution import (
    commit_personal_mcp_change,
    lock_personal_mcp_write,
)
from src.domains.agents.application.personal_mcp_oauth_guard import require_oauth_claim
from src.domains.agents.application.personal_mcp_oauth_schemas import PersonalMCPOAuthPatch
from src.domains.agents.application.personal_mcp_oauth_store import (
    consume_oauth_credentials,
    forget_oauth_claim,
    read_oauth_claim,
    read_oauth_metadata,
    save_oauth_claim,
    save_oauth_metadata,
)
from src.domains.agents.application.secure_continuation import (
    finish_application_continuation,
    note_continuation_claim,
)
from src.domains.agents.application.state_changes import publish_preference_change
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.mcp.personal_state_contract import PersonalMCPWriteCheck
from src.infrastructure.mcp.personal_state_gateway import get_personal_mcp_state


class PersonalMCPOAuthStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    command_id: UUID
    authorization_url: str


async def start_application_personal_mcp_oauth(
    db: AsyncSession,
    actor_id: UUID,
    command_id: UUID,
    origin: ApplicationOrigin | None,
) -> PersonalMCPOAuthStartResponse:
    status = await read_command_status(db, actor_id, command_id, origin)
    if (
        status.operation_id != "personal_mcp.oauth_authorize"
        or status.phase != ApplicationPhase.WAITING
    ):
        raise AuthorizationError(detail={"error_code": "INVALID_INPUT"})
    ticket = await claim_approved_waiting_interaction(db, actor_id, command_id, origin)
    if ticket is None:
        raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})
    try:
        await note_continuation_claim(db, ticket)
        await require_oauth_claim(db, ticket, origin=origin)
        await save_oauth_claim(ticket)
        selected = PersonalMCPOAuthPatch.model_validate(
            ticket.command.draft.intent
        ).personal_mcp_oauth
        starter = get_personal_mcp_state().oauth_start
        if starter is None:
            raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})

        async def check(server_id: UUID, user_id: UUID, linked_id: UUID) -> None:
            if (server_id, user_id, linked_id) != (
                selected.request.server_id,
                actor_id,
                command_id,
            ):
                raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
            await require_oauth_claim(db, ticket, origin=origin)
            await db.rollback()

        result = await starter(
            db,
            actor_id,
            selected.request.server_id,
            application_command_id=command_id,
            application_check=check,
        )
        await save_oauth_metadata(ticket, result.metadata)
        await require_oauth_claim(db, ticket, origin=origin)
        await db.rollback()
        return PersonalMCPOAuthStartResponse(
            command_id=command_id, authorization_url=result.authorization_url
        )
    except BaseException as error:
        await db.rollback()
        await finish_application_continuation(
            ticket, _download_failure(error, PreferenceWriteReceipt())
        )
        await forget_oauth_claim(command_id)
        raise


async def complete_application_personal_mcp_oauth(
    db: AsyncSession,
    actor_id: UUID,
    command_id: UUID,
    origin: ApplicationOrigin | None,
) -> ApplicationCommandStatus:
    # Read authority before the private cache, and lock both durable fences before
    # consuming the token slot. A duplicate finalizer cannot reuse the same tokens.
    status = await read_command_status(db, actor_id, command_id, origin)
    if (
        status.operation_id != "personal_mcp.oauth_authorize"
        or status.phase != ApplicationPhase.RESUMING
    ):
        raise AuthorizationError(detail={"error_code": "INVALID_INPUT"})
    ticket = await read_oauth_claim(command_id)
    await require_oauth_claim(db, ticket, origin=origin, lock=True)
    metadata = await read_oauth_metadata(command_id)
    credentials = await consume_oauth_credentials(command_id)
    if credentials is None:
        await db.rollback()
        raise ResourceConflictError("user_mcp_server", detail={"error_code": "OAUTH_PENDING"})
    draft = ticket.command.draft
    receipt = PreferenceWriteReceipt()
    try:
        selected = PersonalMCPOAuthPatch.model_validate(draft.intent).personal_mcp_oauth
        writer = get_personal_mcp_state().oauth_save
        if writer is None:
            raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})

        async def apply(check: PersonalMCPWriteCheck) -> bool:
            async def fresh(session: AsyncSession) -> None:
                await check(session)
                await require_oauth_claim(session, ticket, origin=origin)

            changed = await writer(
                db,
                actor_id,
                selected.request.server_id,
                credentials,
                metadata,
                expected=selected.expected,
                check=fresh,
            )
            await require_oauth_claim(db, ticket, origin=origin, compare_snapshot=False)
            return changed

        observed: dict[str, JsonValue] = {
            "personal_mcp_oauth": {
                "server_id": str(selected.request.server_id),
                "authorization_saved": True,
                "connection_verified": False,
            }
        }
        await lock_personal_mcp_write(db, actor_id, draft)
        await require_oauth_claim(db, ticket, origin=origin)
        await commit_personal_mcp_change(
            db, actor_id, draft, receipt, apply, committed_values=observed
        )
        outcome = ApplicationExecutionOutcome(
            success=True, phase=ApplicationPhase.COMMITTED, committed=True, values=observed
        )
    except BaseException as error:
        await db.rollback()
        await finish_application_continuation(
            ticket,
            _download_failure(error, receipt).model_copy(update={"values": receipt.values or {}}),
        )
        publish_preference_change(draft, receipt)
        await forget_oauth_claim(command_id)
        raise
    await finish_application_continuation(ticket, outcome)
    publish_preference_change(draft, receipt)
    await forget_oauth_claim(command_id)
    return await read_command_status(db, actor_id, command_id, origin)
