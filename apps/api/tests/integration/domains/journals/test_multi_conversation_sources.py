"""Journal history and activity aggregate the account while preserving dialogue boundaries."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.constants import JOURNAL_CONSOLIDATION_HISTORY_MESSAGE_MAX_CHARS
from src.core.conversation_target import ConversationKind
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.journals import conversation_sources
from tests.fixtures.learning_sources import Sources
from tests.fixtures.learning_sources import sources as sources
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration


@pytest.fixture
async def history(
    async_engine: AsyncEngine,
    sources: Sources,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> Sources:
    """Interleave two topics and insert hidden/foreign rows that must never be read."""
    foreign = await commit_owner(async_engine, committed_user_ids)
    now = datetime.now(UTC)
    async with AsyncSession(async_engine) as db:
        db.add(
            Conversation(
                id=foreign, user_id=foreign, kind=ConversationKind.MAIN, runtime_id=foreign
            )
        )
        await db.flush()
        messages = [
            (sources.main.id, "user", "MAIN QUESTION", False),
            (sources.annex.id, "user", "ANNEX QUESTION", False),
            (sources.main.id, "assistant", "MAIN ANSWER", False),
            (sources.annex.id, "assistant", "ANNEX ANSWER", False),
            (sources.annex.id, "user", "HIDDEN BRIEF", True),
            (foreign, "user", "FOREIGN QUESTION", False),
        ]
        for index, (identity, role, content, hidden) in enumerate(messages):
            db.add(
                ConversationMessage(
                    conversation_id=identity,
                    role=role,
                    content=content,
                    hidden=hidden,
                    created_at=now - timedelta(minutes=len(messages) - index),
                )
            )
        await db.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine) as db:
            yield db

    monkeypatch.setattr("src.domains.journals.conversation_sources.get_db_context", session)
    return sources


async def test_journal_history_has_one_global_limit_and_separates_topics(history: Sources) -> None:
    text = await conversation_sources.load_conversation_history(
        history.main.owner_id, None, max_messages=3, max_days=7
    )
    assert "3 of 4" in text
    assert "MAIN QUESTION" not in text
    assert "HIDDEN BRIEF" not in text and "FOREIGN QUESTION" not in text
    assert text.count("ANNEX QUESTION") == text.count("ANNEX ANSWER") == 1
    assert text.count("MAIN ANSWER") == 1
    # Each block belongs to one discussion, even when timestamps interleave.
    assert str(history.main.id) in text and str(history.annex.id) in text
    assert text.index("ANNEX QUESTION") < text.index("ANNEX ANSWER")
    assert not text.index("ANNEX QUESTION") < text.index("MAIN ANSWER") < text.index("ANNEX ANSWER")


async def test_usage_counts_visible_human_messages_from_every_discussion(history: Sources) -> None:
    text = await conversation_sources.build_usage_patterns_section(history.main.owner_id)
    assert "User messages: 2." in text


async def test_global_page_publishes_body_cuts_and_orders_tied_dates_by_id(
    async_engine: AsyncEngine, history: Sources
) -> None:
    low, high = sorted((uuid4(), uuid4()))
    cap = JOURNAL_CONSOLIDATION_HISTORY_MESSAGE_MAX_CHARS
    now = datetime.now(UTC)
    async with AsyncSession(async_engine) as db:
        db.add_all(
            [
                ConversationMessage(
                    id=low,
                    conversation_id=history.main.id,
                    role="user",
                    content="Older tie",
                    created_at=now,
                ),
                ConversationMessage(
                    id=high,
                    conversation_id=history.annex.id,
                    role="assistant",
                    content="x" * (cap + 5),
                    created_at=now,
                ),
            ]
        )
        await db.commit()
    result = await conversation_sources.load_conversation_history(history.main.owner_id, None, 1, 7)
    assert "1 of 6" in result
    assert "Older tie" not in result
    assert "x" * cap in result and "x" * (cap + 1) not in result
    assert "[excerpt cut]" in result


async def test_unreadable_history_is_not_reported_as_empty(
    history: Sources, monkeypatch: pytest.MonkeyPatch
) -> None:
    @asynccontextmanager
    async def failed_session() -> AsyncIterator[AsyncSession]:
        raise SQLAlchemyError("Injected read failure")
        yield  # pragma: no cover - makes the failure a context-manager entry

    monkeypatch.setattr("src.domains.journals.conversation_sources.get_db_context", failed_session)
    text = await conversation_sources.load_conversation_history(
        history.main.owner_id, None, max_messages=3, max_days=7
    )
    assert "unavailable" in text.lower()
    usage = await conversation_sources.build_usage_patterns_section(history.main.owner_id)
    assert "unavailable" in usage.lower()
