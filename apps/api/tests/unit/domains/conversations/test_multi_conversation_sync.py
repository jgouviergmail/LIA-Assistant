"""Real session events publish every changed discussion after its commit only."""

import asyncio
from collections.abc import Coroutine
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.conversations import sync_signal

pytestmark = pytest.mark.unit


async def test_savepoint_commit_waits_for_outer_commit_and_rollback_keeps_prior_signals() -> None:
    """A released savepoint is not durable; its rollback does not erase prior work."""
    tasks: list[asyncio.Task[None]] = []

    def own(
        coro: Coroutine[object, object, None], *, name: str, independent_of_graph: bool
    ) -> None:
        tasks.append(asyncio.create_task(coro, name=name))

    published = AsyncMock()
    owner, main, annex = UUID(int=1), UUID(int=2), UUID(int=3)
    with (
        patch.object(sync_signal, "safe_fire_and_forget", own),
        patch.object(sync_signal, "_publish", published),
    ):
        async with AsyncSession() as db:
            await db.begin()
            sync_signal.arm_conversation_signal(
                db, user_id=owner, conversation_id=main, kind=sync_signal.CONVERSATION_UPDATED
            )
            async with db.begin_nested():
                sync_signal.arm_conversation_signal(
                    db, user_id=owner, conversation_id=annex, kind=sync_signal.CONVERSATION_UPDATED
                )
            assert not tasks
            await db.rollback()
            assert not tasks
            await db.begin()
            sync_signal.arm_conversation_signal(
                db, user_id=owner, conversation_id=main, kind=sync_signal.CONVERSATION_UPDATED
            )
            nested = await db.begin_nested()
            sync_signal.arm_conversation_signal(
                db, user_id=owner, conversation_id=annex, kind=sync_signal.CONVERSATION_RESET
            )
            await nested.rollback()
            await db.commit()
        await asyncio.gather(*tasks)
    assert [call.args for call in published.await_args_list] == [
        (owner, main, sync_signal.CONVERSATION_UPDATED)
    ]


@pytest.mark.parametrize("rollback", [False, True])
async def test_commit_coalesces_by_owner_and_discussion(rollback: bool) -> None:
    """A reset of A cannot swallow B's update, nor can a rollback announce either."""
    tasks: list[asyncio.Task[None]] = []

    def own(
        coro: Coroutine[object, object, None], *, name: str, independent_of_graph: bool
    ) -> None:
        assert independent_of_graph
        tasks.append(asyncio.create_task(coro, name=name))

    published = AsyncMock()
    owner, main, annex = UUID(int=1), UUID(int=2), UUID(int=3)
    with (
        patch.object(sync_signal, "safe_fire_and_forget", own),
        patch.object(sync_signal, "_publish", published),
    ):
        async with AsyncSession() as db:
            await db.begin()
            changes: tuple[tuple[UUID, sync_signal.SyncKind], ...] = (
                (main, sync_signal.CONVERSATION_UPDATED),
                (annex, sync_signal.CONVERSATION_UPDATED),
                (main, sync_signal.CONVERSATION_RESET),
                (annex, sync_signal.CONVERSATION_UPDATED),
            )
            for target, kind in changes:
                sync_signal.arm_conversation_signal(
                    db, user_id=owner, conversation_id=target, kind=kind
                )
            assert not tasks
            if rollback:
                await db.rollback()
            else:
                await db.commit()
        await asyncio.gather(*tasks)
    observed = {tuple(call.args) for call in published.await_args_list}
    assert observed == (
        set()
        if rollback
        else {
            (owner, main, sync_signal.CONVERSATION_RESET),
            (owner, annex, sync_signal.CONVERSATION_UPDATED),
        }
    )
