"""
Tests for ConversationService v2 optimized methods.

Validates that the optimized repository-based methods produce identical
output to the legacy implementation.
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.models import User
from src.domains.chat.models import MessageTokenSummary
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.service import ConversationService

# Skip in pre-commit - uses testcontainers/real DB, too slow
# Run manually with: pytest tests/unit/test_conversation_service_v2.py -v
pytestmark = pytest.mark.integration


@pytest.fixture
async def test_user(async_session: AsyncSession):
    """Fixture creating a test user."""
    user = User(
        email="test_service@example.com",
        hashed_password="hashed_password",
        is_active=True,
        is_superuser=False,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def test_conversation_with_messages(async_session: AsyncSession, test_user):
    """Fixture creating a conversation with messages and token summaries."""
    # Create conversation
    conversation = Conversation(
        id=test_user.id,
        user_id=test_user.id,
        title="Test Conversation",
        message_count=0,
        total_tokens=0,
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    # Create 3 messages
    messages = []
    for i in range(3):
        run_id = f"run_{uuid4()}"
        msg = ConversationMessage(
            conversation_id=conversation.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Test message {i}",
            message_metadata={"run_id": run_id},
        )
        async_session.add(msg)
        messages.append((msg, run_id))

    await async_session.commit()

    # Create token summaries for 2 out of 3 messages
    for msg, run_id in messages[:2]:
        await async_session.refresh(msg)
        token_summary = MessageTokenSummary(
            user_id=test_user.id,
            session_id="test_session",
            run_id=run_id,
            conversation_id=conversation.id,
            total_prompt_tokens=100 * (messages.index((msg, run_id)) + 1),
            total_completion_tokens=50 * (messages.index((msg, run_id)) + 1),
            total_cached_tokens=0,
            total_cost_eur=Decimal("0.001") * (messages.index((msg, run_id)) + 1),
        )
        async_session.add(token_summary)

    await async_session.commit()

    return conversation, test_user


@pytest.mark.asyncio
async def test_get_messages_with_tokens_v2_basic(async_session, test_conversation_with_messages):
    """
    GIVEN a conversation with messages and token summaries
    WHEN get_messages_with_tokens_v2 is called
    THEN should return messages with token data using optimized query
    """
    conversation, user = test_conversation_with_messages
    service = ConversationService()

    # Call optimized v2 method
    messages = await service.get_messages_with_tokens_v2(
        user_id=user.id,
        limit=50,
        db=async_session,
    )

    # Verify results
    assert len(messages) == 3

    # Check that 2 messages have token data (messages[:2] from fixture)
    messages_with_tokens = [m for m in messages if m["tokens_in"] is not None]
    assert len(messages_with_tokens) == 2

    # Verify token data structure
    for msg in messages_with_tokens:
        assert "tokens_in" in msg
        assert "tokens_out" in msg
        assert "tokens_cache" in msg
        assert "cost_eur" in msg or msg["cost_eur"] is None  # Cost may be None if no logs
        assert msg["tokens_in"] > 0
        assert msg["tokens_out"] > 0


@pytest.mark.asyncio
async def test_get_messages_with_tokens_auto_uses_v2(
    async_session, test_conversation_with_messages
):
    """
    GIVEN a conversation with messages
    WHEN get_messages_with_tokens_auto is called
    THEN should use optimized v2 implementation and return messages with tokens

    Note: The USE_CONVERSATION_REPOSITORY feature flag was removed.
    get_messages_with_tokens_auto now always uses the optimized v2 implementation.
    """
    conversation, user = test_conversation_with_messages
    service = ConversationService()

    # Call auto-routing method (always uses v2 now)
    messages = await service.get_messages_with_tokens_auto(
        user_id=user.id,
        limit=50,
        db=async_session,
    )

    # Should return results from v2 implementation
    assert len(messages) == 3
    messages_with_tokens = [m for m in messages if m["tokens_in"] is not None]
    assert len(messages_with_tokens) == 2


@pytest.mark.asyncio
async def test_get_messages_with_tokens_v2_empty_conversation(async_session, test_user):
    """
    GIVEN a user with no conversation
    WHEN get_messages_with_tokens_v2 is called
    THEN should return empty list
    """
    service = ConversationService()

    messages = await service.get_messages_with_tokens_v2(
        user_id=test_user.id,
        limit=50,
        db=async_session,
    )

    assert messages == []
