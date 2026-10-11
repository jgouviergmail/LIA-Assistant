"""Real independent workers and write failures cannot split the two continuation fences."""

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.domains.agents.application.command_repository import get_command
from src.domains.agents.application.continuation_approval import claim_approved_waiting_interaction
from src.domains.agents.application.outcomes import ApplicationPhase
from src.domains.agents.effects.digest import args_digest, draft_digest
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.effects.repository import ClaimOutcome, EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from tests.integration.test_application_interaction_concurrency import WaitingCase
from tests.integration.test_application_interaction_concurrency import waiting_case as waiting_case

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def approved_case(
    async_engine: AsyncEngine, waiting_case: WaitingCase
) -> AsyncIterator[WaitingCase]:
    case = waiting_case
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as db:
        command = await get_command(db, case.draft.command_id, case.actor_id)
        assert command is not None
        content = case.draft.model_dump(mode="json")
        repository = EffectLedgerRepository(db)
        ticket = await repository.claim(
            ClaimRequest(
                user_id=case.actor_id,
                thread_id=f"continuation-{case.draft.command_id}",
                run_id="the-original-run",
                source="user",
                execution_mode="pipeline",
                tool_name="draft:application_action",
                mutation_policy="draft",
                idempotency_key=f"draft:{command.draft_id}",
                args_digest=args_digest("draft:application_action", {"draft": content}),
                approval_kind="draft_critique",
                approval_ref=command.draft_id,
                draft_digest=draft_digest(content),
            )
        )
        assert ticket.claim_token is not None
        assert await repository.close_waiting(
            ticket.effect.id,
            ticket.claim_token,
            result_payload=case.outcome.model_dump(mode="json"),
        )
        await db.commit()
    yield case


async def test_independent_workers_claim_one_command_and_one_continuation_effect(
    async_engine: AsyncEngine, approved_case: WaitingCase
) -> None:
    case = approved_case
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    start = asyncio.Event()

    async def claim():
        async with maker() as db:
            await start.wait()
            return await claim_approved_waiting_interaction(
                db, case.actor_id, case.draft.command_id, case.origin
            )

    workers = [asyncio.create_task(claim()), asyncio.create_task(claim())]
    start.set()
    results = await asyncio.wait_for(asyncio.gather(*workers), timeout=10)
    winners = [result for result in results if result is not None]
    assert len(winners) == 1 and results.count(None) == 1
    async with maker() as db:
        command = await get_command(db, case.draft.command_id, case.actor_id)
        assert command is not None and command.phase == ApplicationPhase.RESUMING
        assert command.claim_token == winners[0].command.token
        effects = (
            await db.scalars(select(AgentEffect).where(AgentEffect.user_id == case.actor_id))
        ).all()
        assert len(effects) == 2
        assert {effect.status for effect in effects} == {EffectStatus.WAITING, EffectStatus.CLAIMED}


@pytest.mark.parametrize("after_insert", [False, True])
async def test_ledger_failure_rolls_back_the_command_and_any_inserted_effect(
    async_engine: AsyncEngine,
    approved_case: WaitingCase,
    monkeypatch: pytest.MonkeyPatch,
    after_insert: bool,
) -> None:
    case = approved_case
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    actual_claim = EffectLedgerRepository.claim

    async def fail_claim(repository: EffectLedgerRepository, request: ClaimRequest) -> ClaimOutcome:
        if after_insert:
            await actual_claim(repository, request)
        raise SQLAlchemyError("simulated write failure")

    monkeypatch.setattr(EffectLedgerRepository, "claim", fail_claim)
    async with maker() as db:
        with pytest.raises(SQLAlchemyError):
            await claim_approved_waiting_interaction(
                db, case.actor_id, case.draft.command_id, case.origin
            )
    async with maker() as db:
        command = await get_command(db, case.draft.command_id, case.actor_id)
        assert command is not None and command.phase == ApplicationPhase.WAITING
        assert command.claim_token == case.original_token
        effects = (
            await db.scalars(select(AgentEffect).where(AgentEffect.user_id == case.actor_id))
        ).all()
        assert len(effects) == 1 and effects[0].status == EffectStatus.WAITING
