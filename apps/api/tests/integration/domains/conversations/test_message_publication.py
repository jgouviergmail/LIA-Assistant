"""A message publication is bound to the invocation and generation that produced it."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.conversation_execution import ExecutionRevoked, RunAdmission, RunEnd
from src.core.conversation_publication import CurrentPrimaryPublication, PinnedRunPublication
from src.core.conversation_target import ConversationKind
from src.core.run_authority import RunAuthority, run_authority_scope
from src.domains.agents.api.chat_response import partial_finalizer
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.service import ConversationService
from src.infrastructure.database import session
from src.infrastructure.streaming.run_admission import owned_execution

pytestmark = pytest.mark.integration


async def test_a_closed_graph_cannot_archive_a_late_answer(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    async with AsyncSession(async_engine) as db:
        assert await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        await db.commit()
    with run_authority_scope(RunAuthority(reserved)):
        async with AsyncSession(async_engine) as db:
            with pytest.raises(ExecutionRevoked):
                await ConversationService().archive_message(
                    reserved.target.id,
                    "assistant",
                    "A late answer",
                    {"run_id": reserved.run_id},
                    db,
                )


@pytest.mark.parametrize("earlier", ["answer", "partial", "question", "user", "older_stream"])
async def test_a_partial_deduplicates_only_its_own_answer_not_a_question_or_previous_invocation(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    earlier: str,
) -> None:
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )
    metadata: dict[str, object] = {
        "run_id": reserved.run_id,
        "stream_id": str(uuid4()) if earlier == "older_stream" else reserved.stream_id,
    }
    if earlier == "question":
        metadata["hitl_question"] = True
    if earlier == "partial":
        metadata["interrupted"] = True
    async with AsyncSession(async_engine) as db:
        await ConversationService().archive_message(
            reserved.target.id,
            "user" if earlier == "user" else "assistant",
            "Earlier",
            metadata,
            db,
        )
        await db.commit()
    async with owned_execution(reserved):
        finalize = partial_finalizer(reserved)
        await finalize("An observed partial", "cancelled")
        await finalize("An observed partial", "cancelled")
    async with AsyncSession(async_engine) as db:
        rows = (
            await db.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == reserved.target.id,
                )
            )
        ).all()
    assert len(rows) == (1 if earlier in {"answer", "partial"} else 2)
    partials = [row for row in rows if row.content == "An observed partial"]
    if partials:
        assert partials[0].message_metadata is not None
        assert partials[0].message_metadata["stream_id"] == reserved.stream_id


async def test_two_finalizers_commit_only_one_observed_partial(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )
    finalize = partial_finalizer(reserved)
    await asyncio.gather(finalize("Observed", "cancelled"), finalize("Observed", "cancelled"))
    async with AsyncSession(async_engine) as db:
        rows = (
            await db.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == reserved.target.id,
                )
            )
        ).all()
        assert [row.content for row in rows] == ["Observed"]


async def test_an_independent_notification_uses_current_main_while_an_annex_is_occupied(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    main_id = uuid4()
    async with AsyncSession(async_engine) as db:
        db.add(
            Conversation(
                id=main_id,
                user_id=reserved.target.owner_id,
                kind=ConversationKind.MAIN,
                revision=2,
                runtime_id=uuid4(),
                title="Main",
            )
        )
        await db.commit()
        message = await ConversationService().archive_message(
            CurrentPrimaryPublication(reserved.target.owner_id),
            "assistant",
            "A notification",
            None,
            db,
        )
        assert message.conversation_id == main_id
        assert message.message_metadata == {"conversation_revision": 2}
        await db.commit()
        # Publishing does not steal or close the other discussion's graph slot.
        await ConversationExecutionRepository(db).require_current(reserved)


@pytest.mark.parametrize("revoked", [False, True])
async def test_a_graph_result_cannot_disguise_itself_as_an_independent_notification(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    revoked: bool,
) -> None:
    with run_authority_scope(RunAuthority(reserved, revoked=revoked)):
        async with AsyncSession(async_engine) as db:
            with pytest.raises(ExecutionRevoked):
                await ConversationService().archive_message(
                    CurrentPrimaryPublication(reserved.target.owner_id),
                    "assistant",
                    "Late",
                    None,
                    db,
                )


async def test_a_retired_generation_is_never_rebound_when_publishing_a_late_result(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    async with AsyncSession(async_engine) as db:
        await db.execute(
            update(Conversation)
            .where(Conversation.id == reserved.target.id)
            .values(
                revision=reserved.target.revision + 1,
                runtime_id=uuid4(),
            )
        )
        await db.commit()
        with pytest.raises(ExecutionRevoked):
            await ConversationService().archive_message(
                PinnedRunPublication(reserved),
                "assistant",
                "Late",
                None,
                db,
            )


async def test_a_publication_holds_its_generation_until_its_own_transaction_finishes(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    started = asyncio.Event()

    async def rotate() -> None:
        async with AsyncSession(async_engine) as db:
            started.set()
            await db.execute(
                update(Conversation)
                .where(Conversation.id == reserved.target.id)
                .values(
                    revision=reserved.target.revision + 1,
                    runtime_id=uuid4(),
                )
            )
            await db.commit()

    async with AsyncSession(async_engine) as db:
        await ConversationService().archive_message(
            PinnedRunPublication(reserved),
            "assistant",
            "Not committed",
            None,
            db,
        )
        resetting = asyncio.create_task(rotate())
        try:
            await asyncio.wait_for(started.wait(), 1)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(resetting), 0.1)
        finally:
            await db.rollback()
            await asyncio.wait_for(resetting, 3)
        assert (
            await db.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == reserved.target.id,
                )
            )
        ).all() == []
