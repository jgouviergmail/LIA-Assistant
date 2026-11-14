"""History generation locks and indexed deep pages on real PostgreSQL."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, delete, event, insert, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.sql import ClauseElement

from src.core.conversation_selection import ConversationSelection
from src.core.exceptions import ResourceConflictError
from src.domains.chat.models import MessageTokenSummary
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.repository import ConversationRepository
from src.domains.users.models import User
from src.infrastructure.database.errors import database_error_fields
from tests.fixtures.persisted_runtimes import persist_runtime_targets

pytestmark = pytest.mark.integration


@pytest.fixture
async def conversation_with_dated_messages(
    async_session: AsyncSession, test_user: User
) -> Conversation:
    """Space message timestamps so the legacy cut is deterministic."""
    conversation = Conversation(user_id=test_user.id, title="Pagination")
    async_session.add(conversation)
    await async_session.flush()
    base = datetime(2026, 1, 1, 12, tzinfo=UTC)
    for index in range(5):
        async_session.add(
            ConversationMessage(
                conversation_id=conversation.id,
                role="user" if index % 2 == 0 else "assistant",
                content=f"message {index}",
                created_at=base + timedelta(minutes=index),
            )
        )
    await async_session.commit()
    return conversation


async def test_no_cursor_returns_newest_first(
    async_session: AsyncSession, conversation_with_dated_messages: Conversation
) -> None:
    results = await ConversationRepository(async_session).get_messages_with_token_summaries(
        conversation_id=conversation_with_dated_messages.id, limit=3
    )
    assert [message.content for message, _ in results] == ["message 4", "message 3", "message 2"]


async def test_cursor_skips_messages_at_or_after(
    async_session: AsyncSession, conversation_with_dated_messages: Conversation
) -> None:
    identity = conversation_with_dated_messages.id
    repository = ConversationRepository(async_session)
    first = await repository.get_messages_with_token_summaries(conversation_id=identity, limit=3)
    older = await repository.get_messages_with_token_summaries(
        conversation_id=identity, limit=3, before_created_at=first[-1][0].created_at
    )
    assert [message.content for message, _ in older] == ["message 1", "message 0"]


async def test_a_history_generation_cannot_change_between_metadata_and_rows(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    (target,) = await persist_runtime_targets(async_engine, committed_user_ids, count=1)
    selection = ConversationSelection(
        conversation_id=target.id, conversation_revision=target.revision
    )
    async with AsyncSession(async_engine) as writer:
        writer.add(
            ConversationMessage(conversation_id=target.id, role="user", content="Before reset")
        )
        await writer.commit()
        async with AsyncSession(async_engine) as reader:
            current = await ConversationCatalogueService(reader).resolve_target(
                target.owner_id, selection, lock=True
            )
            assert current == target
            await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
            with pytest.raises(DBAPIError) as blocked:
                await writer.execute(
                    update(Conversation)
                    .where(Conversation.id == target.id)
                    .values(revision=target.revision + 1, runtime_id=uuid4())
                )
            assert database_error_fields(blocked.value)["sqlstate"] == "55P03"
            await writer.rollback()
            rows = await ConversationRepository(reader).get_messages_with_token_summaries(target.id)
            assert [message.content for message, _ in rows] == ["Before reset"]
            await reader.commit()
        await writer.execute(
            update(Conversation)
            .where(Conversation.id == target.id)
            .values(revision=target.revision + 1, runtime_id=uuid4())
        )
        await writer.execute(
            delete(ConversationMessage).where(ConversationMessage.conversation_id == target.id)
        )
        await writer.commit()
        with pytest.raises(ResourceConflictError):
            await ConversationCatalogueService(writer).resolve_target(
                target.owner_id, selection, lock=True
            )


def _visited_rows(plan: object) -> int:
    """Count actual rows inspected by every plan node, including filtered ones."""
    assert isinstance(plan, dict)
    rows, removed, loops = (
        plan.get(key, 0) for key in ("Actual Rows", "Rows Removed by Filter", "Actual Loops")
    )
    assert isinstance(rows, int) and isinstance(removed, int) and isinstance(loops, int)
    children = plan.get("Plans", [])
    assert isinstance(children, list)
    return (rows + removed) * loops + sum(_visited_rows(child) for child in children)


async def test_a_deep_history_page_does_not_scan_the_preceding_history(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    (target,) = await persist_runtime_targets(async_engine, committed_user_ids, count=1)
    count, limit = 20000, 20
    stamp = datetime(2026, 11, 10, tzinfo=UTC)
    prefix = uuid4().int & ~((1 << 32) - 1)
    async with AsyncSession(async_engine) as db:
        await db.execute(
            insert(ConversationMessage),
            [
                {
                    "id": UUID(int=prefix + i),
                    "conversation_id": target.id,
                    "role": "assistant",
                    "content": f"Answer {i}",
                    "message_metadata": {"run_id": f"{target.id}-{i // 2}"},
                    "created_at": stamp + timedelta(seconds=i // 2),
                }
                for i in range(count)
            ],
        )
        await db.execute(
            insert(MessageTokenSummary),
            [
                {
                    "user_id": target.owner_id,
                    "conversation_id": target.id,
                    "session_id": "history-performance",
                    "run_id": f"{target.id}-{i}",
                    "total_prompt_tokens": 10,
                }
                for i in range(count // 2)
            ],
        )
        await db.execute(text("ANALYZE conversation_messages"))
        await db.execute(text("ANALYZE message_token_summary"))
        statements: list[ClauseElement] = []

        def capture(
            connection: Connection,
            clause: ClauseElement,
            multiparams: object,
            params: object,
            options: object,
        ) -> None:
            statements.append(clause)

        event.listen(async_engine.sync_engine, "before_execute", capture)
        try:
            rows = await ConversationRepository(db).get_messages_with_token_summaries(
                target.id,
                limit=limit,
                before_created_at=stamp + timedelta(seconds=count // 4),
                before_message_id=UUID(int=prefix + count // 2),
            )
        finally:
            event.remove(async_engine.sync_engine, "before_execute", capture)
        assert len(statements) == 1
        assert [message.id for message, _ in rows] == [
            UUID(int=prefix + i) for i in range(count // 2 - 1, count // 2 - limit - 1, -1)
        ]
        assert sum(tokens is not None for _, tokens in rows) == limit // 2
        sql = str(
            statements[0].compile(
                dialect=async_engine.dialect, compile_kwargs={"literal_binds": True}
            )
        )
        explained = (
            await db.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql))
        ).scalar_one()
        assert isinstance(explained, list) and isinstance(explained[0], dict)
        # Count actual work, not wall-clock noise or the mere existence of an index.
        assert _visited_rows(explained[0]["Plan"]) < limit * 20, explained[0]
