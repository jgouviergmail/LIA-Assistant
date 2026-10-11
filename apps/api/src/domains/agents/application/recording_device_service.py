"""One original-HITL claim and one fenced, explicitly device-reported completion."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, raise_not_found_or_unauthorized
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.command_origin_binding import require_command_origin
from src.domains.agents.application.command_repository import get_command
from src.domains.agents.application.continuation_approval import (
    ApprovedInteractionClaim,
    _original_approval,
    claim_approved_waiting_interaction,
)
from src.domains.agents.application.continuation_settlement import settle_continuation
from src.domains.agents.application.interaction_claim import (
    WaitingInteractionClaim,
    _waiting_payload,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.recording_device_schemas import (
    RecordingDeviceAck,
    RecordingDeviceClaim,
    RecordingDevicePatch,
    recording_ack_matches,
)
from src.domains.agents.effects.models import AgentEffect, EffectStatus


async def claim_recording_device(
    db: AsyncSession, actor_id: UUID, command_id: UUID, origin: ApplicationOrigin | None
) -> RecordingDeviceClaim | None:
    command = await get_command(db, command_id, actor_id)
    if command is None or command.operation_id != "meeting_device.control":
        raise_not_found_or_unauthorized("recording command", command_id)
    ticket = await claim_approved_waiting_interaction(db, actor_id, command_id, origin)
    if ticket is None:
        return None
    return RecordingDeviceClaim(
        command_id=command_id,
        claim_token=ticket.command.token,
        expires_at=ticket.command.draft.expires_at,
        intent=RecordingDevicePatch.model_validate(ticket.command.draft.intent).device_recording,
    )


async def _recording_ticket(
    db: AsyncSession,
    actor_id: UUID,
    command_id: UUID,
    ack: RecordingDeviceAck,
    origin: ApplicationOrigin | None,
) -> ApprovedInteractionClaim:
    await load_actor(db, actor_id)
    command = await get_command(db, command_id, actor_id, lock=True)
    if command is None or command.operation_id != "meeting_device.control":
        raise_not_found_or_unauthorized("recording command", command_id)
    await require_command_origin(command, origin, allow_expired=True, require_device=True)
    await load_actor(db, actor_id)
    if command.phase != ApplicationPhase.RESUMING or command.claim_token != ack.claim_token:
        raise AuthorizationError(detail={"error_code": "STALE_STATE"})
    draft, previous, _, _ = _waiting_payload(command)
    claimed = WaitingInteractionClaim(ack.claim_token, draft, previous)
    original = await _original_approval(db, command, claimed)
    effects = (
        await db.scalars(
            select(AgentEffect)
            .where(
                AgentEffect.user_id == actor_id,
                AgentEffect.thread_id == original.thread_id,
                AgentEffect.idempotency_key
                == f"application-continuation:{original.id}:{command_id}",
                AgentEffect.status == EffectStatus.CLAIMED,
            )
            .limit(2)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    if len(effects) != 1:
        raise AuthorizationError(detail={"error_code": "INVALID_APPROVAL"})
    effect = effects[0]
    return ApprovedInteractionClaim(claimed, effect.id, effect.claim_token)


async def acknowledge_recording_device(
    db: AsyncSession,
    actor_id: UUID,
    command_id: UUID,
    ack: RecordingDeviceAck,
    origin: ApplicationOrigin | None,
) -> ApplicationExecutionOutcome:
    ticket = await _recording_ticket(db, actor_id, command_id, ack, origin)
    intent = RecordingDevicePatch.model_validate(ticket.command.draft.intent).device_recording
    if not recording_ack_matches(intent, ack):
        raise AuthorizationError(detail={"error_code": "INVALID_RESPONSE_FORMAT"})
    success = ack.result == "completed"
    outcome = ApplicationExecutionOutcome(
        success=success,
        phase=ApplicationPhase.COMMITTED if success else ApplicationPhase.FAILED,
        committed=success,
        values={
            "device_reported": True,
            "recorder_phase": ack.phase,
            "meeting_id": str(ack.meeting_id) if ack.meeting_id else None,
            "processing_completed": False,
        },
        error_code=(
            None
            if success
            else ("COMPLETION_UNKNOWN" if ack.result == "unknown" else "CONSTRAINT_VIOLATION")
        ),
    )
    if not await settle_continuation(db, ticket, outcome):
        raise AuthorizationError(detail={"error_code": "STALE_STATE"})
    return outcome
