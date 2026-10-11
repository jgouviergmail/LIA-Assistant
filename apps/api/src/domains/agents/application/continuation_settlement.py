"""Persist both completion facts together; a lost write cannot grant automatic replay."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_repository import (
    close_command,
    get_command,
    matches_command,
)
from src.domains.agents.application.continuation_approval import (
    _APPLICATION_EXECUTOR,
    ApprovedInteractionClaim,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.effects.digest import args_digest, draft_digest
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.effects.repository import EffectLedgerRepository


async def matching_continuation_records(
    db: AsyncSession, ticket: ApprovedInteractionClaim, *, lock: bool = False
) -> bool:
    draft = ticket.command.draft
    command = await get_command(db, draft.command_id, draft.actor_id, lock=lock)
    if command is None or not matches_command(command, draft, command.draft_id):
        return False
    if (command.phase, command.claim_token) != (ApplicationPhase.RESUMING, ticket.command.token):
        return False
    statement = (
        select(AgentEffect)
        .where(AgentEffect.id == ticket.effect_id, AgentEffect.user_id == draft.actor_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    effect: AgentEffect | None = await db.scalar(statement)
    if effect is None:
        return False
    content = draft.model_dump(mode="json")
    return (
        effect.status,
        effect.claim_token,
        effect.tool_name,
        effect.mutation_policy,
        effect.approval_kind,
        effect.approval_ref,
        effect.draft_digest,
        effect.args_digest,
    ) == (
        EffectStatus.CLAIMED,
        ticket.effect_token,
        _APPLICATION_EXECUTOR,
        "draft",
        "draft_critique",
        command.draft_id,
        draft_digest(content),
        args_digest(_APPLICATION_EXECUTOR, {"draft": content}),
    )


async def settle_continuation(
    db: AsyncSession, ticket: ApprovedInteractionClaim, outcome: ApplicationExecutionOutcome
) -> bool:
    """Close only the matching two fences, even if permissions were withdrawn meanwhile.

    This records what already returned. It neither authorizes an effect nor
    serves private results. The original handoff is terminal and never touched.
    """
    if outcome.interaction is not None:
        raise ValueError("A continuation completion cannot grant another waiting interaction")
    try:
        if not await matching_continuation_records(db, ticket, lock=True):
            await db.rollback()
            return False
        draft = ticket.command.draft
        closed_command = await close_command(
            db, draft.command_id, draft.actor_id, ticket.command.token, outcome, commit=False
        )
        repository = EffectLedgerRepository(db)
        payload = outcome.model_dump(mode="json")
        if outcome.success:
            closed_effect = await repository.close_success(
                ticket.effect_id, ticket.effect_token, result_payload=payload
            )
        else:
            closed_effect = await repository.close_failure(
                ticket.effect_id,
                ticket.effect_token,
                error_code=outcome.error_code or outcome.phase.value.upper(),
                result_payload=payload,
            )
        if not closed_command or not closed_effect:
            await db.rollback()
            return False
        await db.commit()
        return True
    except BaseException:
        await db.rollback()
        raise
