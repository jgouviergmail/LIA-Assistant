"""
Unit tests for ConversationRepository.

Tests the new repository layer in isolation without affecting existing service.
These tests validate the repository pattern implementation and query optimization.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.repository import ConversationRepository

# Skip in pre-commit - uses testcontainers/real DB, too slow
# Run manually with: pytest tests/unit/test_conversation_repository.py -v
pytestmark = pytest.mark.integration


@pytest.fixture
async def conversation_repo(async_session: AsyncSession):
    """Fixture providing ConversationRepository instance."""
    return ConversationRepository(async_session)


@pytest.fixture
async def test_user(async_session: AsyncSession):
    """Fixture creating a test user."""
    from src.domains.auth.models import User

    user = User(
        email="test@example.com",
        hashed_password="hashed_password",
        is_active=True,
        is_superuser=False,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def test_conversation(async_session: AsyncSession, test_user):
    """Fixture creating a test conversation."""
    conversation = Conversation(
        id=test_user.id,  # 1:1 mapping
        user_id=test_user.id,
        title="Test Conversation",
        message_count=0,
        total_tokens=0,
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)
    return conversation


@pytest.fixture
async def test_messages(async_session: AsyncSession, test_conversation: Conversation):
    """Fixture creating test messages."""
    messages = []
    for i in range(5):
        message = ConversationMessage(
            conversation_id=test_conversation.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Test message {i}",
            message_metadata={"run_id": f"run_{i}", "test": True},
        )
        messages.append(message)
        async_session.add(message)

    await async_session.commit()

    # Refresh all messages
    for msg in messages:
        await async_session.refresh(msg)

    return messages


class TestConversationRepositoryBasics:
    """Test basic repository operations."""

    @pytest.mark.asyncio
    async def test_repository_initialization(self, async_session):
        """
        GIVEN a database session
        WHEN creating ConversationRepository
        THEN repository should initialize correctly
        """
        repo = ConversationRepository(async_session)

        assert repo is not None
        assert repo.db == async_session
        assert repo.model == Conversation

    @pytest.mark.asyncio
    async def test_get_active_for_user_exists(self, conversation_repo, test_conversation):
        """
        GIVEN an active conversation for a user
        WHEN get_active_for_user is called
        THEN should return the conversation
        """
        result = await conversation_repo.get_active_for_user(test_conversation.user_id)

        assert result is not None
        assert result.id == test_conversation.id
        assert result.user_id == test_conversation.user_id
        assert result.deleted_at is None

    @pytest.mark.asyncio
    async def test_get_active_for_user_not_exists(self, conversation_repo):
        """
        GIVEN no conversation for a user
        WHEN get_active_for_user is called
        THEN should return None
        """
        non_existent_user = uuid4()
        result = await conversation_repo.get_active_for_user(non_existent_user)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_active_for_user_ignores_deleted(
        self, async_session, conversation_repo, test_conversation
    ):
        """
        GIVEN a soft-deleted conversation
        WHEN get_active_for_user is called
        THEN should return None (ignores deleted)
        """
        # Soft delete the conversation
        test_conversation.deleted_at = datetime.now(UTC)
        await async_session.commit()

        result = await conversation_repo.get_active_for_user(test_conversation.user_id)

        assert result is None


class TestConversationRepositoryMessages:
    """Test message retrieval operations."""

    @pytest.mark.asyncio
    async def test_get_messages_for_conversation_all(
        self, conversation_repo, test_conversation, test_messages
    ):
        """
        GIVEN a conversation with messages
        WHEN get_messages_for_conversation is called
        THEN should return all messages
        """
        messages = await conversation_repo.get_messages_for_conversation(
            test_conversation.id,
            limit=100,
        )

        assert len(messages) == 5
        # Default order is DESC (newest first)
        assert messages[0].created_at >= messages[-1].created_at

    @pytest.mark.asyncio
    async def test_get_messages_for_conversation_with_limit(
        self, conversation_repo, test_conversation, test_messages
    ):
        """
        GIVEN a conversation with 5 messages
        WHEN get_messages_for_conversation is called with limit=3
        THEN should return only 3 messages
        """
        messages = await conversation_repo.get_messages_for_conversation(
            test_conversation.id,
            limit=3,
        )

        assert len(messages) == 3

    @pytest.mark.asyncio
    async def test_get_messages_for_conversation_order_asc(
        self, conversation_repo, test_conversation, test_messages
    ):
        """
        GIVEN a conversation with messages
        WHEN get_messages_for_conversation is called with order_desc=False
        THEN should return messages in ascending order (oldest first)
        """
        messages = await conversation_repo.get_messages_for_conversation(
            test_conversation.id,
            limit=100,
            order_desc=False,
        )

        assert len(messages) == 5
        # ASC order: oldest first
        assert messages[0].created_at <= messages[-1].created_at

    @pytest.mark.asyncio
    async def test_get_messages_empty_conversation(self, conversation_repo, test_conversation):
        """
        GIVEN a conversation with no messages
        WHEN get_messages_for_conversation is called
        THEN should return empty list
        """
        messages = await conversation_repo.get_messages_for_conversation(
            test_conversation.id,
            limit=50,
        )

        assert len(messages) == 0
        assert messages == []


class TestConversationRepositoryOptimizations:
    """Test optimized query methods (N+1 fixes)."""

    @pytest.mark.asyncio
    async def test_get_messages_with_token_summaries_no_tokens(
        self, conversation_repo, test_conversation, test_messages
    ):
        """
        GIVEN messages without token summaries
        WHEN get_messages_with_token_summaries is called
        THEN should return messages with None token_summary
        """
        results = await conversation_repo.get_messages_with_token_summaries(
            test_conversation.id,
            limit=50,
        )

        assert len(results) == 5

        # Verify structure
        for message, token_summary in results:
            assert isinstance(message, ConversationMessage)
            # No token summaries created yet
            assert token_summary is None

    @pytest.mark.asyncio
    async def test_get_messages_with_token_summaries_with_tokens(
        self, async_session, conversation_repo, test_user, test_conversation, test_messages
    ):
        """
        GIVEN messages with token summaries
        WHEN get_messages_with_token_summaries is called
        THEN should return messages with token data in single query
        """
        from decimal import Decimal

        from src.domains.chat.models import MessageTokenSummary

        # Create token summary for first message
        test_message = test_messages[0]
        run_id = test_message.message_metadata.get("run_id")

        token_summary = MessageTokenSummary(
            user_id=test_user.id,
            session_id="test_session",
            run_id=run_id,
            conversation_id=test_conversation.id,
            total_prompt_tokens=100,
            total_completion_tokens=50,
            total_cached_tokens=0,
            total_cost_eur=Decimal("0.0009"),
        )
        async_session.add(token_summary)
        await async_session.commit()

        # Query with optimization
        results = await conversation_repo.get_messages_with_token_summaries(
            test_conversation.id,
            limit=50,
        )

        assert len(results) == 5

        # Find the message with token summary
        found_with_tokens = False
        for message, token_dict in results:
            if message.id == test_message.id:
                assert token_dict is not None
                assert token_dict["run_id"] == run_id
                assert token_dict["total_tokens"] == 150  # 100 + 50
                assert token_dict["prompt_tokens"] == 100
                assert token_dict["completion_tokens"] == 50
                assert token_dict["cost_eur"] == 0.0009
                found_with_tokens = True
            else:
                # Other messages don't have token summaries
                assert token_dict is None

        assert found_with_tokens, "Should find message with token summary"

    @pytest.mark.asyncio
    async def test_get_conversation_with_messages_eager_load(
        self, conversation_repo, test_conversation, test_messages
    ):
        """
        GIVEN a conversation with messages
        WHEN get_conversation_with_messages is called
        THEN should return conversation with messages eagerly loaded
        """
        conv = await conversation_repo.get_conversation_with_messages(
            test_conversation.id,
            message_limit=10,
        )

        assert conv is not None
        assert conv.id == test_conversation.id

        # Messages should be loaded (no additional query needed)
        # This is validated by the fact that accessing messages doesn't raise
        assert len(conv.messages) == 5


class TestConversationRepositoryDeletion:
    """Test message deletion operations."""

    @pytest.mark.asyncio
    async def test_delete_messages_for_conversation(
        self, async_session, conversation_repo, test_conversation, test_messages
    ):
        """
        GIVEN a conversation with 5 messages
        WHEN delete_messages_for_conversation is called
        THEN should delete all messages and return count
        """
        # Verify messages exist before deletion
        messages_before = await conversation_repo.get_messages_for_conversation(
            test_conversation.id,
            limit=100,
        )
        assert len(messages_before) == 5

        # Delete messages
        count = await conversation_repo.delete_messages_for_conversation(test_conversation.id)

        assert count == 5

        # Verify messages are deleted
        messages_after = await conversation_repo.get_messages_for_conversation(
            test_conversation.id,
            limit=100,
        )
        assert len(messages_after) == 0

    @pytest.mark.asyncio
    async def test_delete_messages_empty_conversation(self, conversation_repo, test_conversation):
        """
        GIVEN a conversation with no messages
        WHEN delete_messages_for_conversation is called
        THEN should return 0 (no messages deleted)
        """
        count = await conversation_repo.delete_messages_for_conversation(test_conversation.id)

        assert count == 0


class TestConversationRepositoryEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_get_active_for_user_returns_none_for_nonexistent(self, conversation_repo):
        """
        GIVEN a non-existent user ID
        WHEN get_active_for_user is called
        THEN should return None gracefully

        Note: The original test for multiple conversations per user is no longer valid
        because the schema enforces UNIQUE constraint on user_id (1:1 mapping).
        Database won't allow multiple conversations per user.
        """
        non_existent_user_id = uuid4()

        result = await conversation_repo.get_active_for_user(non_existent_user_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_messages_with_limit_zero(
        self, conversation_repo, test_conversation, test_messages
    ):
        """
        GIVEN a conversation with messages
        WHEN get_messages_for_conversation is called with limit=0
        THEN should return all messages (no limit)
        """
        messages = await conversation_repo.get_messages_for_conversation(
            test_conversation.id,
            limit=0,  # No limit
        )

        # With limit=0, query should not apply LIMIT clause
        # This returns all messages
        assert len(messages) == 5
