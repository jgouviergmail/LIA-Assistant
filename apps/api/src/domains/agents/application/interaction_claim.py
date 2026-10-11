"""One fenced continuation of a prior exact approval, never another tool invocation."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_interaction import PendingApplicationInteraction
from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, raise_not_found_or_unauthorized
from src.core.security.utils import decrypt_data
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.command_origin_binding import require_command_origin
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.command_service import CommandRejected, _current_operation
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.feature_switches.guard import require_capability_fresh


@dataclass(frozen=True)
class WaitingInteractionClaim:
    token: UUID
    draft: ApplicationActionDraftContent
    previous_outcome: ApplicationExecutionOutcome


def _waiting_payload(
    command: ApplicationCommand,
) -> tuple[
    ApplicationActionDraftContent,
    ApplicationExecutionOutcome,
    ApplicationOperationSpec,
    PendingApplicationInteraction,
]:
    try:
        draft = ApplicationActionDraftContent.model_validate_json(
            decrypt_data(command.content_encrypted)
        )
        if command.result_encrypted is None:
            raise ValueError("Missing interaction receipt")
        outcome = ApplicationExecutionOutcome.model_validate_json(
            decrypt_data(command.result_encrypted)
        )
        interaction = outcome.interaction
        if (
            interaction is None
            or interaction.interaction_id != command.id
            or interaction.expires_at != command.expires_at
            or command.claim_token is None
            or not matches_command(command, draft, command.draft_id)
        ):
            raise ValueError("Invalid waiting command")
        spec = _current_operation(draft)
        if spec.interaction_kind is not None and interaction.kind != spec.interaction_kind:
            raise ValueError("An operation cannot replace its declared proof requirement")
        return draft, outcome, spec, interaction
    except CommandRejected as exc:
        raise AuthorizationError(detail={"error_code": exc.code}) from None
    except ValueError:
        raise AuthorizationError(detail={"error_code": "INVALID_DRAFT"}) from None


async def claim_waiting_interaction(
    db: AsyncSession,
    actor_id: UUID,
    command_id: UUID,
    origin: ApplicationOrigin | None,
    *,
    commit: bool = True,
) -> WaitingInteractionClaim | None:
    """Claim once; an enclosing ledger transaction may commit both claims together."""
    await require_application_tools(db)
    await load_actor(db, actor_id)
    # Recheck authority after any row-lock wait, before reading or claiming its state.
    command = await get_command(db, command_id, actor_id, lock=True)
    if command is None or command.actor_id != actor_id:
        raise_not_found_or_unauthorized("application command", command_id)
    try:
        spec = APPLICATION_OPERATIONS.get(command.operation_id)
    except KeyError:
        raise AuthorizationError(detail={"error_code": "INVALID_DRAFT"}) from None
    if command.phase != ApplicationPhase.WAITING:
        await _authorize_continuation(db, command, spec, origin, allow_expired=True)
        if commit:
            await db.commit()
        return None
    draft, previous, spec, interaction = _waiting_payload(command)
    await _authorize_continuation(
        db,
        command,
        spec,
        origin,
        recent_step_up=spec.kind == OperationKind.SECURE_HANDOFF or interaction.kind == "secure",
    )
    token = uuid4()
    changed = await db.scalar(
        update(ApplicationCommand)
        .where(
            ApplicationCommand.id == command_id,
            ApplicationCommand.actor_id == actor_id,
            ApplicationCommand.phase == ApplicationPhase.WAITING,
            ApplicationCommand.expires_at > datetime.now(UTC),
            ApplicationCommand.content_digest == command.content_digest,
            ApplicationCommand.origin_binding_encrypted == command.origin_binding_encrypted,
            ApplicationCommand.result_encrypted == command.result_encrypted,
            ApplicationCommand.claim_token == command.claim_token,
        )
        .values(phase=ApplicationPhase.RESUMING, claim_token=token)
        .returning(ApplicationCommand.id)
    )
    if commit:
        await db.commit()
    return WaitingInteractionClaim(token, draft, previous) if changed is not None else None


async def _authorize_continuation(
    db: AsyncSession,
    command: ApplicationCommand,
    spec: ApplicationOperationSpec,
    origin: ApplicationOrigin | None,
    *,
    allow_expired: bool = False,
    recent_step_up: bool = False,
) -> None:
    await require_application_tools(db)
    for capability in spec.required_capabilities:
        await require_capability_fresh(db, capability)
    await load_actor(db, command.actor_id, administrative=spec.administrative)
    await require_command_origin(
        command,
        origin,
        allow_expired=allow_expired,
        recent_step_up=recent_step_up,
        require_device=spec.addressed_device,
    )
    await require_application_tools(db)
    for capability in spec.required_capabilities:
        await require_capability_fresh(db, capability)
    await load_actor(db, command.actor_id, administrative=spec.administrative)
