"""Fresh, transport-bound command observation; no private intent or stored permission."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_interaction import PendingApplicationInteraction
from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, raise_not_found_or_unauthorized
from src.core.security.utils import decrypt_data
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.command_origin_binding import require_command_origin
from src.domains.agents.application.command_repository import get_command
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.feature_switches.guard import require_capability_fresh


class ApplicationCommandStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    command_id: UUID
    operation_id: str
    phase: ApplicationPhase
    expires_at: AwareDatetime
    interaction: PendingApplicationInteraction | None = None
    outcome: ApplicationExecutionOutcome | None = None
    prior_outcome: ApplicationExecutionOutcome | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


def _observed_outcome(command: ApplicationCommand) -> ApplicationExecutionOutcome | None:
    if command.result_encrypted is None:
        if command.phase not in {
            ApplicationPhase.PENDING,
            ApplicationPhase.CLAIMED,
            ApplicationPhase.CANCELLED,
        }:
            raise AuthorizationError(detail={"error_code": "INVALID_DRAFT"})
        return None
    try:
        outcome = ApplicationExecutionOutcome.model_validate_json(
            decrypt_data(command.result_encrypted)
        )
    except ValueError:
        raise AuthorizationError(detail={"error_code": "INVALID_DRAFT"}) from None
    matching_phase = outcome.phase == command.phase or (
        command.phase == ApplicationPhase.RESUMING and outcome.phase == ApplicationPhase.WAITING
    )
    if not matching_phase or (
        outcome.interaction is not None
        and (
            outcome.interaction.interaction_id != command.id
            or outcome.interaction.expires_at != command.expires_at
        )
    ):
        raise AuthorizationError(detail={"error_code": "INVALID_DRAFT"})
    return outcome


def _current_status(command: ApplicationCommand) -> ApplicationCommandStatus:
    outcome = _observed_outcome(command)
    prior = outcome if command.phase == ApplicationPhase.RESUMING else None
    if prior is not None:
        outcome = None
    phase = command.phase
    if command.expires_at <= datetime.now(UTC) and phase in {
        ApplicationPhase.PENDING,
        ApplicationPhase.WAITING,
    }:
        phase = ApplicationPhase.EXPIRED
        if outcome is not None:
            interaction = outcome.interaction
            outcome = ApplicationExecutionOutcome(
                success=False,
                phase=phase,
                committed=outcome.committed,
                values=outcome.values,
                error_code=(
                    "INTERACTION_EXPIRED"
                    if interaction is not None and interaction.kind == "secure"
                    else "COMPLETION_UNKNOWN"
                ),
            )
    return ApplicationCommandStatus(
        command_id=command.id,
        operation_id=command.operation_id,
        phase=phase,
        expires_at=command.expires_at,
        interaction=outcome.interaction if outcome is not None else None,
        outcome=outcome,
        prior_outcome=prior,
    )


async def read_command_status(
    db: AsyncSession,
    actor_id: UUID,
    command_id: UUID,
    origin: ApplicationOrigin | None,
) -> ApplicationCommandStatus:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    command = await get_command(db, command_id, actor_id)
    if command is None or command.actor_id != actor_id:
        raise_not_found_or_unauthorized("application command", command_id)
    try:
        spec = APPLICATION_OPERATIONS.get(command.operation_id)
    except KeyError:
        raise AuthorizationError(detail={"error_code": "INVALID_DRAFT"}) from None
    for capability in spec.required_capabilities:
        await require_capability_fresh(db, capability)
    await load_actor(db, actor_id, administrative=spec.administrative)
    await require_command_origin(
        command, origin, allow_expired=True, require_device=spec.addressed_device
    )
    status = _current_status(command)
    # The last Redis lookup may outlive an operator's or administrator's authority.
    await require_application_tools(db)
    for capability in spec.required_capabilities:
        await require_capability_fresh(db, capability)
    await load_actor(db, actor_id, administrative=spec.administrative)
    return status
