"""The conversation sync signal leaves AFTER the commit, on real PostgreSQL (ADR-320).

What only a real session can prove: ``archive_message`` does not commit, so the
signal must ride the session's own transaction — told before the commit, a tab
would read the old page and conclude nothing changed; told after a rollback, it
would read a page where nothing did.
"""

from __future__ import annotations

import asyncio
import uuid
import warnings
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.domains.conversations import sync_signal
from src.domains.conversations.models import Conversation
from src.domains.conversations.service import ConversationService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def _account(session: AsyncSession, email: str) -> Conversation:
    user = User(email=email, hashed_password="x", is_active=True, is_superuser=False)
    session.add(user)
    await session.flush()
    # The conversation id is NOT the account id: the signal must name the account.
    conversation = Conversation(
        id=uuid.uuid4(), user_id=user.id, title="Sync", message_count=0, total_tokens=0
    )
    session.add(conversation)
    await session.commit()
    return conversation


async def _drain() -> None:
    """Let the fire-and-forget publications run."""
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.fixture
def published() -> Any:
    with patch.object(sync_signal, "publish_to_user", AsyncMock(return_value=True)) as mock:
        yield mock


async def test_the_signal_leaves_after_the_commit_and_names_the_account(
    async_session: AsyncSession, published: AsyncMock
) -> None:
    conversation = await _account(async_session, "sync-commit@test.local")

    await ConversationService().archive_message(
        conversation.id, "assistant", "Hello", {"run_id": "r1"}, async_session
    )
    await _drain()
    published.assert_not_awaited()  # written, not committed: nothing said yet

    await async_session.commit()
    await _drain()

    published.assert_awaited_once_with(
        conversation.user_id,
        {"type": "conversation_updated", "conversation_id": str(conversation.id)},
    )


async def test_a_rolled_back_write_says_nothing(
    async_session: AsyncSession, published: AsyncMock
) -> None:
    conversation = await _account(async_session, "sync-rollback@test.local")

    await ConversationService().archive_message(
        conversation.id, "user", "Lost", None, async_session
    )
    await async_session.rollback()
    await _drain()
    # And the next commit of the same session does not resurrect it.
    await async_session.commit()
    await _drain()

    published.assert_not_awaited()


async def test_several_messages_in_one_transaction_make_one_signal(
    async_session: AsyncSession, published: AsyncMock
) -> None:
    conversation = await _account(async_session, "sync-batch@test.local")
    service = ConversationService()

    await service.archive_message(conversation.id, "user", "Q", None, async_session)
    await service.archive_message(conversation.id, "assistant", "A", None, async_session)
    await async_session.commit()
    await _drain()

    assert published.await_count == 1


async def test_a_hidden_row_announces_nothing(
    async_session: AsyncSession, published: AsyncMock
) -> None:
    # The synthetic question of an out-of-turn run (ADR-276) is shown by no tab.
    conversation = await _account(async_session, "sync-hidden@test.local")

    await ConversationService().archive_message(
        conversation.id, "user", "Synthetic", {"hidden": True}, async_session
    )
    await async_session.commit()
    await _drain()

    published.assert_not_awaited()


async def test_a_reset_wins_over_an_update_in_the_same_transaction(
    async_session: AsyncSession, published: AsyncMock
) -> None:
    conversation = await _account(async_session, "sync-reset@test.local")

    await ConversationService().archive_message(
        conversation.id, "assistant", "Before", None, async_session
    )
    sync_signal.arm_conversation_signal(
        async_session,
        user_id=conversation.user_id,
        conversation_id=conversation.id,
        kind=sync_signal.CONVERSATION_RESET,
    )
    await async_session.commit()
    await _drain()

    published.assert_awaited_once_with(
        conversation.user_id,
        {"type": "conversation_reset", "conversation_id": str(conversation.id)},
    )


async def test_each_commit_of_a_long_lived_session_signals_its_own_writes(
    async_session: AsyncSession, published: AsyncMock
) -> None:
    conversation = await _account(async_session, "sync-twice@test.local")
    service = ConversationService()

    await service.archive_message(conversation.id, "assistant", "One", None, async_session)
    await async_session.commit()
    await service.archive_message(conversation.id, "assistant", "Two", None, async_session)
    await async_session.commit()
    await _drain()

    assert published.await_count == 2


async def test_a_failed_publication_is_counted_never_raised(async_session: AsyncSession) -> None:
    conversation = await _account(async_session, "sync-fail@test.local")
    failing = AsyncMock(side_effect=ConnectionError("redis down"))

    with patch.object(sync_signal, "publish_to_user", failing):
        await ConversationService().archive_message(
            conversation.id, "assistant", "Hi", None, async_session
        )
        await async_session.commit()
        await _drain()

    failing.assert_awaited_once()
    sample = sync_signal.conversation_sync_signals_total.labels(
        kind="conversation_updated", outcome="failed"
    )
    assert sample._value.get() >= 1


async def test_a_commit_outside_any_event_loop_is_counted_and_leaves_no_coroutine() -> None:
    # A synchronous caller (a script) commits with no running loop: nothing can
    # be scheduled, and no coroutine may be created only to be dropped.
    session = Session()
    session.info[sync_signal._PENDING] = {
        uuid.uuid4(): (uuid.uuid4(), sync_signal.CONVERSATION_UPDATED)
    }
    before = sync_signal.conversation_sync_signals_total.labels(
        kind="conversation_updated", outcome="no_loop"
    )._value.get()

    def commit_without_a_loop() -> None:
        sync_signal._after_commit(session)

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # « coroutine was never awaited » would raise
        await asyncio.to_thread(commit_without_a_loop)

    after = sync_signal.conversation_sync_signals_total.labels(
        kind="conversation_updated", outcome="no_loop"
    )._value.get()
    assert after == before + 1
