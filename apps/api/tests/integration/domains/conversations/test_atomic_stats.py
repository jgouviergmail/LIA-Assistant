"""Conversation counters survive concurrent stale readers and transaction rollback."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import ExecutionRevoked, RunAdmission, RunEnd
from src.core.run_authority import RunAuthority, run_authority_scope
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.models import Conversation
from src.domains.conversations.service import ConversationService

pytestmark = pytest.mark.integration


async def test_two_sessions_with_stale_identity_maps_do_not_lose_any_increment(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    async def add(db: AsyncSession, *, messages: int, tokens: int) -> None:
        await ConversationService().increment_conversation_stats(
            reserved.target.id,
            tokens,
            db,
            message_increment=messages,
        )
        await db.commit()

    async with AsyncSession(async_engine) as first, AsyncSession(async_engine) as second:
        before_first = await first.get(Conversation, reserved.target.id)
        before_second = await second.get(Conversation, reserved.target.id)
        assert before_first is not None and before_second is not None
        assert before_first.message_count == before_second.message_count == 0
        await asyncio.gather(add(first, messages=2, tokens=11), add(second, messages=3, tokens=23))
    async with AsyncSession(async_engine) as db:
        row = await db.get(Conversation, reserved.target.id)
        assert row is not None
        assert (row.message_count, row.total_tokens) == (5, 34)


async def test_rolled_back_stats_never_become_visible(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    async with AsyncSession(async_engine) as db:
        await ConversationService().increment_conversation_stats(reserved.target.id, 12, db)
        await db.rollback()
    async with AsyncSession(async_engine) as db:
        row = await db.get(Conversation, reserved.target.id)
        assert row is not None and (row.message_count, row.total_tokens) == (0, 0)


async def test_a_closed_invocation_cannot_increment_a_later_generations_stats(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        await db.commit()
        with run_authority_scope(RunAuthority(reserved)), pytest.raises(ExecutionRevoked):
            await ConversationService().increment_conversation_stats(reserved.target.id, 12, db)
