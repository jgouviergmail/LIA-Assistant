"""The mutable status and immutable completion receipt close atomically or stay unresolved."""

from dataclasses import replace
from importlib import import_module
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.domains.agents.application.command_repository import get_command
from src.domains.agents.application.continuation_approval import claim_approved_waiting_interaction
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from tests.integration.test_application_continuation_atomic import approved_case as approved_case
from tests.integration.test_application_interaction_concurrency import WaitingCase
from tests.integration.test_application_interaction_concurrency import waiting_case as waiting_case

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    ["none", "command_token", "effect_token", "lost_write", "mixed_records", "failed"],
)
async def test_completion_settles_both_records_without_rewriting_the_original_handoff(
    async_engine: AsyncEngine,
    approved_case: WaitingCase,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    module = import_module("src.domains.agents.application.continuation_settlement")
    case = approved_case
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as db:
        ticket = await claim_approved_waiting_interaction(
            db, case.actor_id, case.draft.command_id, case.origin
        )
        assert ticket is not None
    supplied = ticket
    if intervention == "command_token":
        supplied = replace(ticket, command=replace(ticket.command, token=uuid4()))
    elif intervention == "effect_token":
        supplied = replace(ticket, effect_token=uuid4())
    elif intervention == "mixed_records":
        async with maker() as db:
            other = await EffectLedgerRepository(db).claim(
                ClaimRequest(
                    user_id=case.actor_id,
                    thread_id="another-thread",
                    run_id="another-run",
                    source="user",
                    execution_mode="react",
                    tool_name="draft:application_action",
                    mutation_policy="draft",
                    idempotency_key="another-continuation",
                    args_digest="0" * 64,
                    approval_kind="draft_critique",
                    approval_ref="another-draft",
                    draft_digest="0" * 64,
                )
            )
            assert other.claim_token is not None
            supplied = replace(ticket, effect_id=other.effect.id, effect_token=other.claim_token)
            await db.commit()
    elif intervention == "lost_write":
        actual_close = EffectLedgerRepository.close_success

        async def lose_write(
            repository: EffectLedgerRepository, effect_id: UUID, token: UUID, **kwargs: object
        ) -> bool:
            await actual_close(repository, effect_id, token, **kwargs)
            raise RuntimeError("simulated receipt write failure")

        monkeypatch.setattr(EffectLedgerRepository, "close_success", lose_write)
    completion = (
        ApplicationExecutionOutcome(
            success=False,
            phase=ApplicationPhase.FAILED,
            committed=True,
            error_code="POST_COMMIT_FAILURE",
            values={"already_saved": True},
        )
        if intervention == "failed"
        else ApplicationExecutionOutcome(
            success=True,
            phase=ApplicationPhase.COMMITTED,
            committed=True,
            values={"device_acknowledged": True},
        )
    )
    async with maker() as db:
        if intervention == "lost_write":
            with pytest.raises(RuntimeError, match="simulated receipt"):
                await module.settle_continuation(db, supplied, completion)
        else:
            assert await module.settle_continuation(db, supplied, completion) is (
                intervention in {"none", "failed"}
            )
    async with maker() as db:
        command = await get_command(db, case.draft.command_id, case.actor_id)
        effect = await db.get(AgentEffect, ticket.effect_id)
        assert command is not None and effect is not None
        if intervention in {"none", "failed"}:
            assert command.phase == completion.phase and effect.status == (
                EffectStatus.SUCCEEDED if completion.success else EffectStatus.FAILED
            )
            assert EffectLedgerRepository.decrypted_result(effect) == completion.model_dump(
                mode="json"
            )
            assert not await module.settle_continuation(db, supplied, completion)
        else:
            assert (
                command.phase == ApplicationPhase.RESUMING and effect.status == EffectStatus.CLAIMED
            )
            if intervention == "mixed_records":
                other_effect = await db.get(AgentEffect, supplied.effect_id)
                assert other_effect is not None and other_effect.status == EffectStatus.CLAIMED
