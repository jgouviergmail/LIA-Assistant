"""A run's bill joins the discussion its words are written in (2026-11-14).

A call's spend starts outside any discussion — its lookups during the call, its
synthesis after it — so its bill names none, and a bill naming none shows under
Main alone. Since a call placed from an annex returns there (ADR-378 amendment
2026-11-14), the return's bubble in the annex showed no cost, and no
discussion's totals counted the call. The door writing the run's words names
the bill's discussion; a bill already named keeps its own.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_publication import OriginPublication
from src.core.conversation_target import ConversationOrigin, ConversationRef
from src.core.field_names import FIELD_RUN_ID, FIELD_TOTAL_COST_EUR
from src.domains.chat.models import MessageTokenSummary
from src.domains.conversations.models import Conversation
from src.domains.conversations.repository import ConversationRepository
from src.domains.conversations.run_bills import attach_run_bill
from src.domains.conversations.service import ConversationService
from tests.fixtures.persisted_runtimes import persist_annex_with_main

pytestmark = pytest.mark.integration

_COST = Decimal("0.031000")


async def _bill(engine: AsyncEngine, owner_id: UUID, *, conversation_id: UUID | None = None) -> str:
    """A call's bill as its first writer files it: no discussion, unless one is given."""
    run_id = f"phone_call_{uuid4().hex}"
    async with AsyncSession(engine) as db:
        db.add(
            MessageTokenSummary(
                user_id=owner_id,
                session_id="phone",
                run_id=run_id,
                conversation_id=conversation_id,
                total_prompt_tokens=1200,
                total_completion_tokens=300,
                total_cached_tokens=0,
                total_cost_eur=_COST,
            )
        )
        await db.commit()
    return run_id


async def _named(engine: AsyncEngine, run_id: str) -> UUID | None:
    async with AsyncSession(engine) as db:
        return await db.scalar(
            select(MessageTokenSummary.conversation_id).where(MessageTokenSummary.run_id == run_id)
        )


async def _attach(
    engine: AsyncEngine,
    owner_id: UUID,
    run_id: str,
    conversation_id: UUID,
    *,
    revision: int | None = None,
) -> bool:
    async with AsyncSession(engine) as db:
        attached = await attach_run_bill(
            db, owner_id=owner_id, run_id=run_id, conversation_id=conversation_id, revision=revision
        )
        await db.commit()
        return attached


async def test_a_bill_naming_no_discussion_joins_the_annex_its_words_go_to(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    annex, _main = await persist_annex_with_main(async_engine, committed_user_ids)
    run_id = await _bill(async_engine, annex.owner_id)

    assert await _attach(async_engine, annex.owner_id, run_id, annex.id, revision=annex.revision)
    assert await _named(async_engine, run_id) == annex.id


async def test_a_bill_already_named_keeps_its_discussion(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    annex, main_id = await persist_annex_with_main(async_engine, committed_user_ids)
    run_id = await _bill(async_engine, annex.owner_id, conversation_id=main_id)

    assert not await _attach(async_engine, annex.owner_id, run_id, annex.id)
    assert await _named(async_engine, run_id) == main_id


async def test_an_annex_is_named_only_while_the_generation_its_words_go_to_lives(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    annex, _main = await persist_annex_with_main(async_engine, committed_user_ids)
    run_id = await _bill(async_engine, annex.owner_id)

    # Reset since the return was decided: the generation the words go to is gone.
    assert not await _attach(
        async_engine, annex.owner_id, run_id, annex.id, revision=annex.revision - 1
    )
    assert await _named(async_engine, run_id) is None


async def test_a_deleted_annex_is_never_named(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    annex, _main = await persist_annex_with_main(async_engine, committed_user_ids)
    run_id = await _bill(async_engine, annex.owner_id)
    async with AsyncSession(async_engine) as db:
        await db.execute(
            update(Conversation)
            .where(Conversation.id == annex.id)
            .values(deleted_at=datetime.now(UTC))
        )
        await db.commit()

    assert not await _attach(
        async_engine, annex.owner_id, run_id, annex.id, revision=annex.revision
    )
    assert await _named(async_engine, run_id) is None


async def test_another_accounts_bill_is_never_named(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    mine, _my_main = await persist_annex_with_main(async_engine, committed_user_ids)
    theirs, _their_main = await persist_annex_with_main(async_engine, committed_user_ids)
    their_run = await _bill(async_engine, theirs.owner_id)

    assert not await _attach(async_engine, mine.owner_id, their_run, mine.id)
    assert await _named(async_engine, their_run) is None


async def _return_in(engine: AsyncEngine, annex: ConversationRef, run_id: str) -> UUID:
    """The call's return, written where its act began, under the call's run id."""
    async with AsyncSession(engine) as db:
        message = await ConversationService().archive_message(
            OriginPublication(annex.owner_id, ConversationOrigin.of(annex)),
            "assistant",
            "I called the garage and left a message.",
            {FIELD_RUN_ID: run_id},
            db,
        )
        await attach_run_bill(
            db, owner_id=annex.owner_id, run_id=run_id, conversation_id=message.conversation_id
        )
        message_id = message.id  # read before the commit expires the row
        await db.commit()
        return message_id


async def test_the_annex_shows_the_call_cost_under_its_return_and_counts_it(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    """What the person sees: the bubble's cost and the discussion's total."""
    annex, _main = await persist_annex_with_main(async_engine, committed_user_ids)
    run_id = await _bill(async_engine, annex.owner_id)
    message_id = await _return_in(async_engine, annex, run_id)

    async with AsyncSession(async_engine) as db:
        repository = ConversationRepository(db)
        rows = await repository.get_messages_with_token_summaries(annex.id, limit=10)
        bubbles = {message.id: summary for message, summary in rows}
        totals = await repository.get_token_totals(annex)

    assert bubbles[message_id] is not None
    assert Decimal(str(totals[FIELD_TOTAL_COST_EUR])) == _COST
