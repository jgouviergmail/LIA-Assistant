"""A real completion writer owns its SQL session even while the requesting task is cancelled."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.domains.agents.application import secure_continuation
from src.domains.agents.application.command_repository import get_command
from src.domains.agents.application.continuation_approval import (
    ApprovedInteractionClaim,
    claim_approved_waiting_interaction,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from tests.integration.test_application_continuation_atomic import approved_case as approved_case
from tests.integration.test_application_interaction_concurrency import WaitingCase
from tests.integration.test_application_interaction_concurrency import waiting_case as waiting_case

pytestmark = pytest.mark.integration


async def test_cancellation_waits_for_one_completion_in_its_own_real_database_session(
    async_engine: AsyncEngine,
    approved_case: WaitingCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = approved_case
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as db:
        ticket = await claim_approved_waiting_interaction(
            db, case.actor_id, case.draft.command_id, case.origin
        )
        assert ticket is not None
    entered = asyncio.Event()
    finish = asyncio.Event()
    closed = asyncio.Event()
    writers: list[AsyncSession] = []
    actual_settle = secure_continuation.settle_continuation

    @asynccontextmanager
    async def own_session() -> AsyncIterator[AsyncSession]:
        async with maker() as writer:
            writers.append(writer)
            try:
                yield writer
            finally:
                closed.set()

    async def pause_settlement(
        writer: AsyncSession,
        claimed: ApprovedInteractionClaim,
        outcome: ApplicationExecutionOutcome,
    ) -> bool:
        entered.set()
        await finish.wait()
        return await actual_settle(writer, claimed, outcome)

    monkeypatch.setattr(secure_continuation, "get_db_context", own_session)
    monkeypatch.setattr(secure_continuation, "settle_continuation", pause_settlement)
    completion = ApplicationExecutionOutcome(
        success=True, phase=ApplicationPhase.COMMITTED, committed=True
    )
    caller = asyncio.create_task(
        secure_continuation.finish_application_continuation(ticket, completion)
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        caller.cancel()
        await asyncio.sleep(0)
        assert not closed.is_set()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(caller, timeout=5)
        assert closed.is_set() and len(writers) == 1
        async with maker() as observer:
            command = await get_command(observer, case.draft.command_id, case.actor_id)
            effect = await observer.get(AgentEffect, ticket.effect_id)
            assert command is not None and command.phase == ApplicationPhase.COMMITTED
            assert effect is not None and effect.status == EffectStatus.SUCCEEDED
    finally:
        finish.set()
        if not caller.done():
            caller.cancel()
        await asyncio.gather(caller, return_exceptions=True)
