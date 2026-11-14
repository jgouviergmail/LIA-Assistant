"""Committed SQL updates in several discussions announce only durable outer results."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.conversations import sync_signal
from src.domains.conversations.models import Conversation
from tests.fixtures.learning_sources import Sources
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("rollback_outer", [False, True])
async def test_savepoint_changes_announce_only_after_durable_outer_commit(
    async_engine: AsyncEngine, sources: Sources, rollback_outer: bool
) -> None:
    """Real PostgreSQL SAVEPOINT release cannot announce an uncommitted row."""
    published = AsyncMock(return_value=True)
    with patch.object(sync_signal, "publish_to_user", published):
        async with AsyncSession(async_engine) as db:
            for target in (sources.main, sources.annex):
                async with db.begin_nested():
                    await db.execute(
                        update(Conversation)
                        .where(Conversation.id == target.id)
                        .values(title="Committed test title")
                    )
                    sync_signal.arm_conversation_signal(
                        db,
                        user_id=target.owner_id,
                        conversation_id=target.id,
                        kind=sync_signal.CONVERSATION_UPDATED,
                    )
            await asyncio.sleep(0)
            published.assert_not_awaited()
            if rollback_outer:
                await db.rollback()
            else:
                await db.commit()
        for _ in range(5):
            await asyncio.sleep(0)
    observed = {call.args[1]["conversation_id"] for call in published.await_args_list}
    assert observed == (set() if rollback_outer else {str(sources.main.id), str(sources.annex.id)})
