"""Atomically claim a continuation under the original immutable exact-HITL receipt."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.constants import AGENT_EFFECT_SCHEMA_VERSION
from src.core.exceptions import AuthorizationError
from src.core.security.utils import decrypt_data
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.command_repository import get_command
from src.domains.agents.application.interaction_claim import (
    WaitingInteractionClaim,
    _authorize_continuation,
    claim_waiting_interaction,
)
from src.domains.agents.application.operation_spec import OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.effects.digest import args_digest, payload_digest
from src.domains.agents.effects.labels import build_effect_label
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest

_APPLICATION_EXECUTOR = "draft:application_action"
_RECEIPT = TypeAdapter(dict[str, JsonValue])


@dataclass(frozen=True)
class ApprovedInteractionClaim:
    command: WaitingInteractionClaim
    effect_id: UUID
    effect_token: UUID


def _reject_approval() -> AuthorizationError:
    return AuthorizationError(detail={"error_code": "INVALID_APPROVAL"})


async def _original_approval(
    db: AsyncSession, command: ApplicationCommand, claimed: WaitingInteractionClaim
) -> AgentEffect:
    # Draft ids are globally unique in the command table. Two originating threads
    # claiming the same draft are ambiguous authority, not two reusable approvals.
    effects = (
        await db.scalars(
            select(AgentEffect)
            .where(
                AgentEffect.user_id == command.actor_id,
                AgentEffect.idempotency_key == f"draft:{command.draft_id}",
            )
            .limit(2)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    if len(effects) != 1:
        raise _reject_approval()
    effect = effects[0]
    expected = (
        _APPLICATION_EXECUTOR,
        "draft",
        "draft_critique",
        command.draft_id,
        command.content_digest,
        args_digest(_APPLICATION_EXECUTOR, {"draft": claimed.draft.model_dump(mode="json")}),
        EffectStatus.WAITING,
        AGENT_EFFECT_SCHEMA_VERSION,
    )
    actual = (
        effect.tool_name,
        effect.mutation_policy,
        effect.approval_kind,
        effect.approval_ref,
        effect.draft_digest,
        effect.args_digest,
        effect.status,
        effect.schema_version,
    )
    if actual != expected or effect.closed_at is None or effect.error_code is not None:
        raise _reject_approval()
    _validate_waiting_receipt(effect, claimed.previous_outcome)
    return effect


def _validate_waiting_receipt(effect: AgentEffect, previous: ApplicationExecutionOutcome) -> None:
    if effect.result_payload is None or effect.result_truncated:
        raise _reject_approval()
    try:
        payload = _RECEIPT.validate_json(decrypt_data(effect.result_payload))
        outcome = ApplicationExecutionOutcome.model_validate(payload)
    except ValueError:
        raise _reject_approval() from None
    if payload_digest(payload) != effect.result_digest or outcome != previous:
        raise _reject_approval()


async def claim_approved_waiting_interaction(
    db: AsyncSession,
    actor_id: UUID,
    command_id: UUID,
    origin: ApplicationOrigin | None,
) -> ApprovedInteractionClaim | None:
    """Own this transaction: persist both fences before allowing any external effect.

    A crash or lost acknowledgement leaves a claimed continuation, never an
    automatically replayable action. The original WAITING event stays immutable.
    """
    try:
        claimed = await claim_waiting_interaction(db, actor_id, command_id, origin, commit=False)
        if claimed is None:
            await db.commit()
            return None
        command = await get_command(db, command_id, actor_id)
        if command is None:
            raise _reject_approval()
        original = await _original_approval(db, command, claimed)
        ticket = await EffectLedgerRepository(db).claim(
            ClaimRequest(
                user_id=actor_id,
                thread_id=original.thread_id,
                run_id=original.run_id,
                source=original.source.value,
                execution_mode=original.execution_mode,
                tool_name=_APPLICATION_EXECUTOR,
                mutation_policy="draft",
                idempotency_key=f"application-continuation:{original.id}:{command_id}",
                args_digest=original.args_digest,
                approval_kind=original.approval_kind,
                approval_ref=original.approval_ref,
                draft_digest=original.draft_digest,
                catalogue_fingerprint=original.catalogue_fingerprint,
                label=build_effect_label(
                    _APPLICATION_EXECUTOR, {"draft": claimed.draft.model_dump(mode="json")}
                ),
            )
        )
        if not ticket.claimed or ticket.claim_token is None:
            raise _reject_approval()
        spec = APPLICATION_OPERATIONS.get(command.operation_id)
        await _authorize_continuation(
            db,
            command,
            spec,
            origin,
            recent_step_up=spec.kind == OperationKind.SECURE_HANDOFF
            or (
                claimed.previous_outcome.interaction is not None
                and claimed.previous_outcome.interaction.kind == "secure"
            ),
        )
        result = ApprovedInteractionClaim(claimed, ticket.effect.id, ticket.claim_token)
        await db.commit()
        return result
    except BaseException:
        await db.rollback()
        raise
