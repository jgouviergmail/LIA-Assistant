"""Unit tests for keyset pagination (scroll-up) on conversation messages.

Covers the ``before_created_at`` cursor on
``ConversationRepository.get_messages_with_token_summaries`` and the
``has_more`` / ``next_cursor`` computation in the
``GET /conversations/me/messages`` router.

Repository tests need PostgreSQL (real ILIKE + ORDER BY ... LIMIT semantics)
and are marked ``integration``. Router tests are pure unit (mocked service)
and run in the fast pre-commit unit suite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.repository import ConversationRepository

# ---------------------------------------------------------------------------
# Repository — integration (real PostgreSQL via async_session fixture)
# ---------------------------------------------------------------------------


@pytest.fixture
async def conversation_with_dated_messages(async_session: AsyncSession):
    """Create a conversation with 5 messages spaced 1 minute apart.

    The explicit ``created_at`` spacing ensures deterministic cursor ordering
    (avoids the microsecond-collision risk when Postgres defaults run too
    close together inside a single test transaction).
    """
    from src.domains.auth.models import User

    user = User(
        email="pagination_user@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    conversation = Conversation(
        id=user.id, user_id=user.id, title="P", message_count=0, total_tokens=0
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    for i in range(5):
        msg = ConversationMessage(
            conversation_id=conversation.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"message {i}",
            created_at=base + timedelta(minutes=i),
        )
        async_session.add(msg)
    await async_session.commit()

    return conversation


@pytest.mark.integration
class TestRepositoryPaginationCursor:
    """``before_created_at`` keyset cursor on get_messages_with_token_summaries."""

    @pytest.mark.asyncio
    async def test_no_cursor_returns_newest_first(
        self, async_session: AsyncSession, conversation_with_dated_messages
    ):
        """Without cursor: returns the ``limit`` newest messages, DESC order."""
        conversation = conversation_with_dated_messages
        repo = ConversationRepository(async_session)

        results = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id, limit=3
        )

        contents = [msg.content for msg, _ in results]
        # 5 messages exist (0..4); top 3 newest are 4, 3, 2
        assert contents == ["message 4", "message 3", "message 2"]

    @pytest.mark.asyncio
    async def test_cursor_skips_messages_at_or_after(
        self, async_session: AsyncSession, conversation_with_dated_messages
    ):
        """With cursor=oldest of previous page: returns strictly older messages."""
        conversation = conversation_with_dated_messages
        repo = ConversationRepository(async_session)

        # Page 1: 3 newest (4, 3, 2). Cursor = created_at of message 2.
        page1 = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id, limit=3
        )
        cursor = page1[-1][0].created_at

        # Page 2: strictly older than cursor → messages 1 and 0
        page2 = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id, limit=3, before_created_at=cursor
        )

        contents = [msg.content for msg, _ in page2]
        assert contents == ["message 1", "message 0"]

    @pytest.mark.asyncio
    async def test_cursor_combined_with_search(
        self, async_session: AsyncSession, conversation_with_dated_messages
    ):
        """``before_created_at`` and ``search`` combine via AND (both filters apply)."""
        conversation = conversation_with_dated_messages
        repo = ConversationRepository(async_session)

        # First page with search "message" matches all 5; cursor = oldest of top 2
        page1 = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id, limit=2, search="message"
        )
        assert [msg.content for msg, _ in page1] == ["message 4", "message 3"]
        cursor = page1[-1][0].created_at

        # Second page: still filtered by "message" AND older than cursor
        page2 = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id,
            limit=10,
            search="message",
            before_created_at=cursor,
        )
        assert [msg.content for msg, _ in page2] == [
            "message 2",
            "message 1",
            "message 0",
        ]


# ---------------------------------------------------------------------------
# Router — pure unit (service mocked); validates has_more / next_cursor logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_has_more_true_when_service_returns_limit_plus_one():
    """When service returns ``limit + 1`` rows, router exposes has_more=True
    and truncates the response to ``limit``."""
    from src.domains.conversations import router as router_module
    from src.domains.conversations.router import get_conversation_messages

    base_dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    # Service returns limit+1 = 4 rows (DESC, newest first)
    fake_messages = [
        {
            "id": uuid4(),
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"m{i}",
            "message_metadata": None,
            "created_at": base_dt - timedelta(minutes=i),
            "tokens_in": None,
            "tokens_out": None,
            "tokens_cache": None,
            "cost_eur": None,
            "google_api_requests": None,
        }
        for i in range(4)
    ]
    fake_conv = MagicMock(id=uuid4())
    fake_user = MagicMock(id=uuid4())

    service_mock = MagicMock()
    service_mock.get_active_conversation = AsyncMock(return_value=fake_conv)
    service_mock.get_messages_with_tokens_auto = AsyncMock(return_value=fake_messages)

    with patch.object(router_module, "ConversationService", return_value=service_mock):
        response = await get_conversation_messages(
            limit=3,
            search=None,
            before=None,
            current_user=fake_user,
            db=MagicMock(),
        )

    assert response.has_more is True
    assert len(response.messages) == 3  # Truncated from 4
    # next_cursor = created_at of the oldest item in the returned page (index 2)
    assert response.next_cursor == fake_messages[2]["created_at"]


@pytest.mark.asyncio
async def test_router_has_more_false_when_service_returns_under_limit():
    """When the service returns fewer rows than ``limit``, no more pages exist:
    has_more=False and next_cursor=None."""
    from src.domains.conversations import router as router_module
    from src.domains.conversations.router import get_conversation_messages

    base_dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    fake_messages = [
        {
            "id": uuid4(),
            "role": "user",
            "content": f"m{i}",
            "message_metadata": None,
            "created_at": base_dt - timedelta(minutes=i),
            "tokens_in": None,
            "tokens_out": None,
            "tokens_cache": None,
            "cost_eur": None,
            "google_api_requests": None,
        }
        for i in range(2)
    ]
    fake_conv = MagicMock(id=uuid4())
    fake_user = MagicMock(id=uuid4())

    service_mock = MagicMock()
    service_mock.get_active_conversation = AsyncMock(return_value=fake_conv)
    service_mock.get_messages_with_tokens_auto = AsyncMock(return_value=fake_messages)

    with patch.object(router_module, "ConversationService", return_value=service_mock):
        response = await get_conversation_messages(
            limit=5,
            search=None,
            before=None,
            current_user=fake_user,
            db=MagicMock(),
        )

    assert response.has_more is False
    assert response.next_cursor is None
    assert len(response.messages) == 2


@pytest.mark.asyncio
async def test_router_requests_limit_plus_one_from_service():
    """Router asks the service for ``limit + 1`` rows to detect has_more without
    a second COUNT query — contract relied on by the pagination implementation."""
    from src.domains.conversations import router as router_module
    from src.domains.conversations.router import get_conversation_messages

    fake_conv = MagicMock(id=uuid4())
    fake_user = MagicMock(id=uuid4())

    service_mock = MagicMock()
    service_mock.get_active_conversation = AsyncMock(return_value=fake_conv)
    service_mock.get_messages_with_tokens_auto = AsyncMock(return_value=[])

    with patch.object(router_module, "ConversationService", return_value=service_mock):
        await get_conversation_messages(
            limit=50,
            search=None,
            before=None,
            current_user=fake_user,
            db=MagicMock(),
        )

    call = service_mock.get_messages_with_tokens_auto.call_args
    # All args forwarded as kwargs — assert the limit was bumped by one
    assert call.kwargs["limit"] == 51


@pytest.mark.asyncio
async def test_router_propagates_before_cursor_to_service():
    """The ``before`` query param is forwarded to the service as
    ``before_created_at`` so the keyset filter applies."""
    from src.domains.conversations import router as router_module
    from src.domains.conversations.router import get_conversation_messages

    cursor = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)
    fake_conv = MagicMock(id=uuid4())
    fake_user = MagicMock(id=uuid4())

    service_mock = MagicMock()
    service_mock.get_active_conversation = AsyncMock(return_value=fake_conv)
    service_mock.get_messages_with_tokens_auto = AsyncMock(return_value=[])

    with patch.object(router_module, "ConversationService", return_value=service_mock):
        await get_conversation_messages(
            limit=50,
            search=None,
            before=cursor,
            current_user=fake_user,
            db=MagicMock(),
        )

    call = service_mock.get_messages_with_tokens_auto.call_args
    assert call.kwargs["before_created_at"] == cursor
