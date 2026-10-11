"""Independent SQL workers cannot duplicate a continuation or reuse withdrawn authority."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.application_interaction import PendingApplicationInteraction
from src.core.application_origin import ApplicationOrigin, ApplicationSessionFacts
from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.core.security.utils import encrypt_data
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.command_repository import (
    claim_command,
    close_command,
    get_command,
    save_command,
)
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.interaction_claim import claim_waiting_interaction
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.preparation import prepare_preference_content
from src.domains.agents.application.schemas import PreferencePatch
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class WaitingCase:
    actor_id: UUID
    draft: ApplicationActionDraftContent
    origin: ApplicationOrigin
    original_token: UUID
    outcome: ApplicationExecutionOutcome


@pytest_asyncio.fixture
async def waiting_case(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[WaitingCase]:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    store = SessionStore(await get_redis_session())
    actor_id = uuid4()
    session = await store.create_session(str(actor_id))
    origin = bind_browser_session(actor_id, session.session_id)
    assert origin is not None
    try:
        async with maker() as db:
            db.add(User(id=actor_id, email=f"resume-{actor_id}@example.test", is_active=True))
            await db.commit()
            draft = await prepare_preference_content(db, actor_id, PreferencePatch(font_size=17))
            await save_command(db, draft, f"draft-{uuid4()}", origin=origin)
            await db.commit()
            token = await claim_command(db, draft.command_id, actor_id)
            assert token is not None
            outcome = ApplicationExecutionOutcome(
                success=False,
                phase=ApplicationPhase.WAITING,
                committed=True,
                values={"already_saved": True},
                interaction=PendingApplicationInteraction(
                    interaction_id=draft.command_id, kind="device", expires_at=draft.expires_at
                ),
            )
            assert await close_command(db, draft.command_id, actor_id, token, outcome)
        yield WaitingCase(actor_id, draft, origin, token, outcome)
    finally:
        await store.delete_session(session.session_id)
        async with maker() as db:
            await db.execute(delete(User).where(User.id == actor_id))
            await db.commit()


async def test_two_independent_workers_grant_one_continuation_and_preserve_partial_truth(
    async_engine: AsyncEngine, waiting_case: WaitingCase
) -> None:
    case = waiting_case
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    start = asyncio.Event()

    async def claim():
        async with maker() as db:
            await start.wait()
            return await claim_waiting_interaction(
                db, case.actor_id, case.draft.command_id, case.origin
            )

    tasks = [asyncio.create_task(claim()), asyncio.create_task(claim())]
    start.set()
    results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    winners = [result for result in results if result is not None]
    assert len(winners) == 1 and results.count(None) == 1
    winner = winners[0]
    assert winner.token != case.original_token
    assert winner.previous_outcome == case.outcome
    async with maker() as db:
        status = await read_command_status(db, case.actor_id, case.draft.command_id, case.origin)
        assert status.phase == ApplicationPhase.RESUMING
        assert status.interaction is None and status.outcome is None
        assert status.prior_outcome == case.outcome
        completion = ApplicationExecutionOutcome(
            success=True,
            phase=ApplicationPhase.COMMITTED,
            committed=True,
            values={"already_saved": True, "device_acknowledged": True},
        )
        assert not await close_command(
            db, case.draft.command_id, case.actor_id, case.original_token, completion
        )
        assert await close_command(
            db, case.draft.command_id, case.actor_id, winner.token, completion
        )
        assert not await close_command(
            db, case.draft.command_id, case.actor_id, winner.token, completion
        )


async def test_actor_withdrawal_during_live_origin_read_prevents_claim(
    async_engine: AsyncEngine, waiting_case: WaitingCase
) -> None:
    case = waiting_case
    maker = async_sessionmaker(async_engine, expire_on_commit=False)

    async def withdraw_then_read() -> ApplicationSessionFacts | None:
        async with maker() as operator:
            actor = await operator.get(User, case.actor_id)
            assert actor is not None
            actor.is_active = False
            await operator.commit()
        return await case.origin.read_current()

    origin = ApplicationOrigin(case.actor_id, case.origin.binding_id, withdraw_then_read)
    async with maker() as db:
        with pytest.raises(AuthorizationError):
            await claim_waiting_interaction(db, case.actor_id, case.draft.command_id, origin)
        await db.rollback()
        row = await get_command(db, case.draft.command_id, case.actor_id)
        assert row is not None and row.phase == ApplicationPhase.WAITING
        assert row.claim_token == case.original_token


async def test_disable_while_waiting_for_command_lock_prevents_continuation(
    async_engine: AsyncEngine, waiting_case: WaitingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = waiting_case
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    started = asyncio.Event()

    async def claim() -> None:
        async with maker() as db:
            started.set()
            await claim_waiting_interaction(db, case.actor_id, case.draft.command_id, case.origin)

    async with maker() as blocker:
        await blocker.scalar(
            select(ApplicationCommand)
            .where(ApplicationCommand.id == case.draft.command_id)
            .with_for_update()
        )
        task = asyncio.create_task(claim())
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            await asyncio.sleep(0.05)
            assert not task.done()
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            await blocker.rollback()
            with pytest.raises(AuthorizationError):
                await asyncio.wait_for(task, timeout=5)
        finally:
            await blocker.rollback()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with maker() as db:
        row = await get_command(db, case.draft.command_id, case.actor_id)
        assert row is not None and row.phase == ApplicationPhase.WAITING
        assert row.claim_token == case.original_token


@pytest.mark.parametrize("corruption", ["receipt", "digest", "claim_token"])
async def test_corrupted_waiting_authority_is_never_claimed(
    async_engine: AsyncEngine, waiting_case: WaitingCase, corruption: str
) -> None:
    case = waiting_case
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as db:
        row = await get_command(db, case.draft.command_id, case.actor_id)
        assert row is not None
        if corruption == "receipt":
            row.result_encrypted = encrypt_data(
                case.outcome.model_copy(
                    update={
                        "interaction": case.outcome.interaction.model_copy(
                            update={"interaction_id": uuid4()}
                        )
                    }
                ).model_dump_json()
            )
        elif corruption == "digest":
            row.content_digest = "0" * 64
        else:
            row.claim_token = None
        await db.commit()
        with pytest.raises(AuthorizationError):
            await claim_waiting_interaction(db, case.actor_id, case.draft.command_id, case.origin)
        await db.rollback()
        saved = await get_command(db, case.draft.command_id, case.actor_id)
        assert saved is not None and saved.phase == ApplicationPhase.WAITING
