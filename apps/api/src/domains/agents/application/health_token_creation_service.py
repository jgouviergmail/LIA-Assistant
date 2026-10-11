"""Only the approved source browser can receive one ephemeral token secret."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.continuation_approval import claim_approved_waiting_interaction
from src.domains.agents.application.export_download_service import _download_failure
from src.domains.agents.application.health_token_creation import (
    authorize_health_token_creation,
    canonical_health_token_creation,
)
from src.domains.agents.application.health_token_creation_schemas import HealthTokenCreatePatch
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.secure_continuation import (
    finish_application_continuation,
    note_continuation_claim,
)
from src.domains.agents.application.state_changes import publish_preference_change
from src.domains.health_metrics.schemas import HealthMetricTokenCreateResponse
from src.domains.health_metrics.token_creation_commands import (
    HealthTokenCreationCompletionUnknown,
    create_managed_health_token,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def serve_health_token_creation(
    db: AsyncSession, actor_id: UUID, command_id: UUID, origin: ApplicationOrigin | None
) -> HealthMetricTokenCreateResponse:
    status = await read_command_status(db, actor_id, command_id, origin)
    if status.operation_id != "health_token.create" or status.phase != ApplicationPhase.WAITING:
        raise AuthorizationError(detail={"error_code": "INVALID_INPUT"})
    ticket = await claim_approved_waiting_interaction(db, actor_id, command_id, origin)
    if ticket is None:
        raise ResourceConflictError("health_token", detail={"error_code": "STALE_STATE"})
    receipt = PreferenceWriteReceipt()
    draft = ticket.command.draft

    async def check() -> None:
        await authorize_health_token_creation(db, actor_id, origin)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    try:
        await note_continuation_claim(db, ticket)
        if not canonical_health_token_creation(draft):
            raise ValueError("Token creation requires exact approved source configuration")
        intent = HealthTokenCreatePatch.model_validate(draft.intent)
        try:
            secret = await create_managed_health_token(
                db, actor_id, command_id, intent.health_token_to_create.label, receipt, check
            )
        except HealthTokenCreationCompletionUnknown as error:
            raise CommandRejected("COMPLETION_UNKNOWN") from error
        outcome = ApplicationExecutionOutcome(
            success=True,
            phase=ApplicationPhase.COMMITTED,
            committed=True,
            values=receipt.values or {},
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
    await check()
    return secret
