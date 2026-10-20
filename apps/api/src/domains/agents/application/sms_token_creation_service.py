"""Only the approved source browser can receive one ephemeral token secret."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.continuation_approval import claim_approved_waiting_interaction
from src.domains.agents.application.continuation_failure import application_continuation_failure
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.secure_continuation import (
    finish_application_continuation,
    note_continuation_claim,
)
from src.domains.agents.application.sms_action_schemas import SmsTokenCreatePatch
from src.domains.agents.application.sms_actions import (
    authorize_sms_management,
    canonical_sms_action,
)
from src.domains.agents.application.state_changes import publish_preference_change
from src.domains.ingestion.schemas import IngestionTokenSecret
from src.domains.ingestion.token_commands import (
    IngestionTokenCompletionUnknown,
    create_managed_token,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def serve_sms_token_creation(
    db: AsyncSession, actor_id: UUID, command_id: UUID, origin: ApplicationOrigin | None
) -> IngestionTokenSecret:
    status = await read_command_status(db, actor_id, command_id, origin)
    if status.operation_id != "sms_token.create" or status.phase != ApplicationPhase.WAITING:
        raise AuthorizationError(detail={"error_code": "INVALID_INPUT"})
    ticket = await claim_approved_waiting_interaction(db, actor_id, command_id, origin)
    if ticket is None:
        raise ResourceConflictError("sms_token", detail={"error_code": "STALE_STATE"})
    receipt = PreferenceWriteReceipt()
    draft = ticket.command.draft

    async def check() -> None:
        await authorize_sms_management(db, actor_id, origin, browser=True)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    try:
        await note_continuation_claim(db, ticket)
        if not canonical_sms_action(draft):
            raise ValueError("Token creation requires exact approved source configuration")
        intent = SmsTokenCreatePatch.model_validate(draft.intent)
        try:
            secret = await create_managed_token(
                db,
                actor_id,
                command_id,
                intent.ingestion_token_to_create.label,
                intent.ingestion_token_to_create.source_id,
                receipt,
                check,
            )
        except IngestionTokenCompletionUnknown as error:
            raise CommandRejected("COMPLETION_UNKNOWN") from error
        outcome = ApplicationExecutionOutcome(
            success=True,
            phase=ApplicationPhase.COMMITTED,
            committed=True,
            values=receipt.values or {},
        )
    except BaseException as error:
        await db.rollback()
        failed = application_continuation_failure(error, receipt).model_copy(
            update={"values": receipt.values or {}}
        )
        await finish_application_continuation(ticket, failed)
        publish_preference_change(draft, receipt)
        raise
    await finish_application_continuation(ticket, outcome)
    publish_preference_change(draft, receipt)
    await check()
    return secret
