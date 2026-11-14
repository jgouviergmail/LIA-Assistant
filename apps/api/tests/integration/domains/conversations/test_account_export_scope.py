"""The streaming account export includes every discussion and no retired or foreign row."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_target import ConversationKind
from src.domains.account_export import builder
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.conversations.models import Conversation, ConversationMessage
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration


async def test_export_pages_all_discussions_and_never_recreates_retired_messages(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the actual server cursor across a partition boundary, then reset one source."""
    owner = await commit_owner(async_engine, committed_user_ids)
    foreign = await commit_owner(async_engine, committed_user_ids)
    targets = [owner, uuid4(), uuid4()]
    async with AsyncSession(async_engine) as db:
        for identity in [*targets, foreign]:
            db.add(
                Conversation(
                    id=identity,
                    user_id=foreign if identity == foreign else owner,
                    kind=(
                        ConversationKind.MAIN
                        if identity in (owner, foreign)
                        else ConversationKind.SECONDARY
                    ),
                    runtime_id=uuid4(),
                    title="Fictional export discussion",
                )
            )
        await db.flush()
        for identity in [*targets, foreign]:
            for index in range(31):
                db.add(
                    ConversationMessage(
                        conversation_id=identity,
                        role="user" if index % 2 == 0 else "assistant",
                        content=f"Fictional export row {index}",
                        hidden=index == 0,
                    )
                )
        await db.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine) as db:
            yield db

    monkeypatch.setattr(builder, "get_db_context", session)
    before = [row async for row in builder._iter_table_rows("conversation_messages", owner)]
    assert len(before) == 93
    assert {row["conversation_id"] for row in before} == set(targets)
    assert sum(row["hidden"] is True for row in before) == 3

    async with AsyncSession(async_engine) as db:
        await ConversationLifecycle(db).request_reset(
            owner, targets[1], operation_id=uuid4(), expected_revision=0
        )
    after = [row async for row in builder._iter_table_rows("conversation_messages", owner)]
    assert len(after) == 62
    assert {row["id"] for row in after} == {
        row["id"] for row in before if row["conversation_id"] != targets[1]
    }
