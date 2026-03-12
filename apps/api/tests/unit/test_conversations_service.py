"""
Comprehensive unit tests for ConversationService.

Coverage target: 85%+ from 10%

This test suite covers:
- HITL filtering logic (static methods)
- Conversation CRUD operations
- Message management (archive, update, retrieve)
- Statistics tracking
- Token and cost calculation
- Audit logging
- Feature flag routing
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.field_names import (
    FIELD_TOTAL_COST_EUR,
    FIELD_TOTAL_TOKENS_CACHE,
    FIELD_TOTAL_TOKENS_IN,
    FIELD_TOTAL_TOKENS_OUT,
)
from src.domains.auth.models import User
from src.domains.chat.models import MessageTokenSummary
from src.domains.conversations.models import (
    Conversation,
    ConversationAuditLog,
    ConversationMessage,
)
from src.domains.conversations.service import ConversationService

# Skip in pre-commit - uses testcontainers/real DB, too slow
# Run manually with: pytest tests/unit/test_conversations_service.py -v
pytestmark = pytest.mark.integration

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def sample_user(async_session: AsyncSession) -> User:
    """Create sample user for testing."""
    user = User(
        email="test@example.com",
        hashed_password="hash",
        full_name="Test User",
        is_active=True,
        is_verified=True,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def sample_conversation(
    async_session: AsyncSession,
    sample_user: User,
) -> Conversation:
    """Create sample conversation for testing."""
    conversation = Conversation(
        id=sample_user.id,
        user_id=sample_user.id,
        title="Test Conversation",
        message_count=0,
        total_tokens=0,
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)
    return conversation


@pytest.fixture
def service() -> ConversationService:
    """Create service instance."""
    return ConversationService()


# ============================================================================
# Static Method Tests: HITL Filtering Logic (NOW DISABLED)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestHITLFiltering:
    """Test HITL approval filtering static methods - NOW DISABLED.

    HITL message filtering is disabled. All messages are shown and counted.
    These tests verify that no filtering occurs.
    """

    def test_should_not_filter_hitl_approve(self, service):
        """Test HITL APPROVE messages are NOT filtered (filtering disabled)."""
        assert not service._should_filter_hitl_message(
            role="user",
            metadata={"hitl_response": True, "decision_type": "APPROVE"},
        )

    def test_should_not_filter_hitl_edit(self, service):
        """Test HITL EDIT messages are NOT filtered."""
        assert not service._should_filter_hitl_message(
            role="user",
            metadata={"hitl_response": True, "decision_type": "EDIT"},
        )

    def test_should_not_filter_hitl_reject(self, service):
        """Test HITL REJECT messages are NOT filtered."""
        assert not service._should_filter_hitl_message(
            role="user",
            metadata={"hitl_response": True, "decision_type": "REJECT"},
        )

    def test_should_not_filter_assistant(self, service):
        """Test assistant messages are NOT filtered."""
        assert not service._should_filter_hitl_message(
            role="assistant",
            metadata={"hitl_response": True, "decision_type": "APPROVE"},
        )

    def test_should_not_filter_no_metadata(self, service):
        """Test messages without metadata are NOT filtered."""
        assert not service._should_filter_hitl_message(role="user", metadata=None)

    def test_should_not_filter_empty_metadata(self, service):
        """Test messages with empty metadata are NOT filtered."""
        assert not service._should_filter_hitl_message(role="user", metadata={})

    def test_filter_hitl_messages_keeps_all_messages(self, service, sample_conversation):
        """Test filtering keeps ALL messages (filtering disabled)."""
        messages = [
            ConversationMessage(
                id=uuid4(),
                conversation_id=sample_conversation.id,
                role="user",
                content="hello",
                message_metadata=None,
            ),
            ConversationMessage(
                id=uuid4(),
                conversation_id=sample_conversation.id,
                role="user",
                content="oui",  # APPROVE - now kept
                message_metadata={"hitl_response": True, "decision_type": "APPROVE"},
            ),
            ConversationMessage(
                id=uuid4(),
                conversation_id=sample_conversation.id,
                role="assistant",
                content="response",
                message_metadata=None,
            ),
        ]

        filtered = service._filter_hitl_messages(messages)

        # All 3 messages should be kept (no filtering)
        assert len(filtered) == 3
        assert filtered[0].content == "hello"
        assert filtered[1].content == "oui"  # APPROVE now kept
        assert filtered[2].content == "response"

    def test_filter_hitl_messages_keeps_edit(self, service, sample_conversation):
        """Test filtering keeps HITL EDIT messages."""
        messages = [
            ConversationMessage(
                id=uuid4(),
                conversation_id=sample_conversation.id,
                role="user",
                content="non recherche paul",
                message_metadata={"hitl_response": True, "decision_type": "EDIT"},
            ),
        ]

        filtered = service._filter_hitl_messages(messages)

        assert len(filtered) == 1
        assert filtered[0].content == "non recherche paul"

    def test_filter_hitl_messages_empty_list(self, service):
        """Test filtering empty list returns empty list."""
        filtered = service._filter_hitl_messages([])
        assert len(filtered) == 0

    def test_filter_hitl_messages_dict_keeps_all_messages(self, service):
        """Test filtering keeps ALL dict messages (filtering disabled)."""
        messages = [
            {"role": "user", "content": "hello", "message_metadata": None},
            {
                "role": "user",
                "content": "oui",
                "message_metadata": {"hitl_response": True, "decision_type": "APPROVE"},
            },
            {"role": "assistant", "content": "response", "message_metadata": None},
        ]

        filtered = service._filter_hitl_messages_dict(messages)

        # All 3 messages should be kept (no filtering)
        assert len(filtered) == 3
        assert filtered[0]["content"] == "hello"
        assert filtered[1]["content"] == "oui"  # APPROVE now kept
        assert filtered[2]["content"] == "response"

    def test_filter_hitl_messages_dict_empty(self, service):
        """Test filtering empty dict list."""
        filtered = service._filter_hitl_messages_dict([])
        assert len(filtered) == 0


# ============================================================================
# get_or_create_conversation Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetOrCreateConversation:
    """Test get_or_create_conversation method."""

    async def test_creates_new_conversation(self, service, sample_user, async_session):
        """Test creating new conversation when none exists."""
        conversation = await service.get_or_create_conversation(
            user_id=sample_user.id,
            db=async_session,
        )

        assert conversation is not None
        assert conversation.id == sample_user.id
        assert conversation.user_id == sample_user.id
        assert conversation.message_count == 0
        assert conversation.total_tokens == 0
        assert conversation.deleted_at is None
        assert "Conversation du" in conversation.title

    async def test_returns_existing_conversation(
        self, service, sample_user, sample_conversation, async_session
    ):
        """Test returning existing conversation instead of creating new one."""
        conversation = await service.get_or_create_conversation(
            user_id=sample_user.id,
            db=async_session,
        )

        assert conversation.id == sample_conversation.id
        assert conversation.title == "Test Conversation"

    async def test_creates_audit_log_for_new_conversation(
        self, service, sample_user, async_session
    ):
        """Test audit log is created when creating new conversation."""
        conversation = await service.get_or_create_conversation(
            user_id=sample_user.id,
            db=async_session,
        )

        # Verify audit log created
        from sqlalchemy import select

        stmt = select(ConversationAuditLog).where(
            ConversationAuditLog.conversation_id == conversation.id,
            ConversationAuditLog.action == "created",
        )
        result = await async_session.execute(stmt)
        audit_log = result.scalar_one_or_none()

        assert audit_log is not None
        assert audit_log.action == "created"
        assert audit_log.message_count_at_action == 0


# ============================================================================
# get_active_conversation Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetActiveConversation:
    """Test get_active_conversation method."""

    async def test_returns_active_conversation(
        self, service, sample_user, sample_conversation, async_session
    ):
        """Test returns active conversation."""
        conversation = await service.get_active_conversation(
            user_id=sample_user.id,
            db=async_session,
        )

        assert conversation is not None
        assert conversation.id == sample_conversation.id

    async def test_returns_none_when_no_conversation(self, service, sample_user, async_session):
        """Test returns None when no conversation exists."""
        conversation = await service.get_active_conversation(
            user_id=sample_user.id,
            db=async_session,
        )

        assert conversation is None

    async def test_ignores_soft_deleted_conversation(self, service, sample_user, async_session):
        """Test ignores soft-deleted conversations."""
        # Create soft-deleted conversation
        deleted_conv = Conversation(
            id=sample_user.id,
            user_id=sample_user.id,
            title="Deleted",
            message_count=5,
            total_tokens=100,
            deleted_at=datetime.now(UTC),
        )
        async_session.add(deleted_conv)
        await async_session.commit()

        # Should return None (soft-deleted is ignored)
        conversation = await service.get_active_conversation(
            user_id=sample_user.id,
            db=async_session,
        )

        assert conversation is None


# ============================================================================
# archive_message Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestArchiveMessage:
    """Test archive_message method."""

    async def test_archives_user_message(self, service, sample_conversation, async_session):
        """Test archiving user message."""
        message = await service.archive_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="Hello, how are you?",
            metadata=None,
            db=async_session,
        )
        await async_session.commit()

        assert message is not None
        assert message.role == "user"
        assert message.content == "Hello, how are you?"
        assert message.conversation_id == sample_conversation.id

    async def test_archives_message_with_metadata(
        self, service, sample_conversation, async_session
    ):
        """Test archiving message with metadata."""
        metadata = {
            "run_id": "test-run-123",
            "intention": "search",
            "confidence": 0.95,
        }

        message = await service.archive_message(
            conversation_id=sample_conversation.id,
            role="assistant",
            content="I found 3 contacts",
            metadata=metadata,
            db=async_session,
        )
        await async_session.commit()

        assert message.message_metadata is not None
        assert message.message_metadata["run_id"] == "test-run-123"
        assert message.message_metadata["intention"] == "search"

    async def test_archives_assistant_message(self, service, sample_conversation, async_session):
        """Test archiving assistant message."""
        message = await service.archive_message(
            conversation_id=sample_conversation.id,
            role="assistant",
            content="I'm doing well, thank you!",
            metadata={"tokens_in": 10, "tokens_out": 20},
            db=async_session,
        )
        await async_session.commit()

        assert message.role == "assistant"
        assert message.message_metadata["tokens_in"] == 10


# ============================================================================
# update_last_user_message Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestUpdateLastUserMessage:
    """Test update_last_user_message method."""

    async def test_updates_last_user_message(self, service, sample_conversation, async_session):
        """Test updating last user message content."""
        # Create initial message
        await service.archive_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="recherche jean",
            metadata=None,
            db=async_session,
        )
        await async_session.commit()

        # Update message
        updated = await service.update_last_user_message(
            conversation_id=sample_conversation.id,
            new_content="recherche jean",
            metadata_updates={"hitl_edit": True},
            db=async_session,
        )

        assert updated is not None
        assert updated.content == "recherche jean"
        assert updated.message_metadata["hitl_edit"] is True
        assert updated.message_metadata["hitl_original_content"] == "recherche jean"

    async def test_preserves_original_metadata(self, service, sample_conversation, async_session):
        """Test preserves original metadata when updating."""
        # Create message with metadata
        await service.archive_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="original",
            metadata={"run_id": "abc123", "intention": "search"},
            db=async_session,
        )
        await async_session.commit()

        # Update message
        updated = await service.update_last_user_message(
            conversation_id=sample_conversation.id,
            new_content="updated",
            metadata_updates={"hitl_edit": True},
            db=async_session,
        )

        assert updated.message_metadata["run_id"] == "abc123"
        assert updated.message_metadata["intention"] == "search"
        assert updated.message_metadata["hitl_edit"] is True

    async def test_returns_none_when_no_user_message(
        self, service, sample_conversation, async_session
    ):
        """Test returns None when no user message exists."""
        updated = await service.update_last_user_message(
            conversation_id=sample_conversation.id,
            new_content="new content",
            metadata_updates=None,
            db=async_session,
        )

        assert updated is None

    async def test_ignores_assistant_messages(self, service, sample_conversation, async_session):
        """Test only updates user messages, not assistant messages."""
        # Create assistant message only
        await service.archive_message(
            conversation_id=sample_conversation.id,
            role="assistant",
            content="assistant response",
            metadata=None,
            db=async_session,
        )
        await async_session.commit()

        # Should not update assistant message
        updated = await service.update_last_user_message(
            conversation_id=sample_conversation.id,
            new_content="new content",
            metadata_updates=None,
            db=async_session,
        )

        assert updated is None


# ============================================================================
# increment_conversation_stats Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestIncrementConversationStats:
    """Test increment_conversation_stats method."""

    async def test_increments_stats(self, service, sample_conversation, async_session):
        """Test incrementing conversation statistics."""
        await service.increment_conversation_stats(
            conversation_id=sample_conversation.id,
            tokens=100,
            db=async_session,
        )
        await async_session.commit()

        await async_session.refresh(sample_conversation)
        assert sample_conversation.message_count == 1
        assert sample_conversation.total_tokens == 100

    async def test_accumulates_stats(self, service, sample_conversation, async_session):
        """Test stats accumulate across multiple updates."""
        await service.increment_conversation_stats(
            conversation_id=sample_conversation.id,
            tokens=100,
            db=async_session,
        )
        await async_session.commit()

        await service.increment_conversation_stats(
            conversation_id=sample_conversation.id,
            tokens=150,
            db=async_session,
        )
        await async_session.commit()

        await async_session.refresh(sample_conversation)
        assert sample_conversation.message_count == 2
        assert sample_conversation.total_tokens == 250

    async def test_handles_nonexistent_conversation(self, service, async_session):
        """Test gracefully handles nonexistent conversation."""
        fake_id = uuid4()
        # Should not raise exception
        await service.increment_conversation_stats(
            conversation_id=fake_id,
            tokens=100,
            db=async_session,
        )


# ============================================================================
# get_messages Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetMessages:
    """Test get_messages method."""

    async def test_returns_empty_for_no_conversation(self, service, sample_user, async_session):
        """Test returns empty list when no conversation exists."""
        messages = await service.get_messages(
            user_id=sample_user.id,
            limit=50,
            db=async_session,
        )

        assert len(messages) == 0

    async def test_returns_messages_newest_first(
        self, service, sample_user, sample_conversation, async_session
    ):
        """Test messages returned in descending order (newest first)."""
        # Create 3 messages
        for i in range(3):
            await service.archive_message(
                conversation_id=sample_conversation.id,
                role="user",
                content=f"Message {i + 1}",
                metadata=None,
                db=async_session,
            )
        await async_session.commit()

        messages = await service.get_messages(
            user_id=sample_user.id,
            limit=10,
            db=async_session,
        )

        assert len(messages) == 3
        assert messages[0].content == "Message 3"
        assert messages[1].content == "Message 2"
        assert messages[2].content == "Message 1"

    async def test_respects_limit(self, service, sample_user, sample_conversation, async_session):
        """Test pagination limit is respected."""
        # Create 5 messages
        for i in range(5):
            await service.archive_message(
                conversation_id=sample_conversation.id,
                role="user",
                content=f"Message {i + 1}",
                metadata=None,
                db=async_session,
            )
        await async_session.commit()

        messages = await service.get_messages(
            user_id=sample_user.id,
            limit=2,
            db=async_session,
        )

        assert len(messages) == 2
        assert messages[0].content == "Message 5"
        assert messages[1].content == "Message 4"

    async def test_shows_all_messages_with_hide_hitl_flag(
        self, service, sample_user, sample_conversation, async_session
    ):
        """Test ALL messages shown even with hide_hitl_approvals=True (filtering disabled)."""
        # Create mixed messages
        await service.archive_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="hello",
            metadata=None,
            db=async_session,
        )
        await service.archive_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="oui",  # APPROVE - now kept
            metadata={"hitl_response": True, "decision_type": "APPROVE"},
            db=async_session,
        )
        await service.archive_message(
            conversation_id=sample_conversation.id,
            role="assistant",
            content="response",
            metadata=None,
            db=async_session,
        )
        await async_session.commit()

        # Even with hide_hitl_approvals=True, all messages are returned (filtering disabled)
        messages = await service.get_messages(
            user_id=sample_user.id,
            limit=10,
            db=async_session,
            hide_hitl_approvals=True,
        )

        # All 3 messages should be returned (no filtering)
        assert len(messages) == 3
        assert messages[0].content == "response"
        assert messages[1].content == "oui"  # APPROVE now kept
        assert messages[2].content == "hello"

    async def test_shows_all_messages_by_default(
        self, service, sample_user, sample_conversation, async_session
    ):
        """Test all messages shown by default (hide_hitl_approvals=False)."""
        # Create mixed messages
        await service.archive_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="hello",
            metadata=None,
            db=async_session,
        )
        await service.archive_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="oui",  # APPROVE - kept
            metadata={"hitl_response": True, "decision_type": "APPROVE"},
            db=async_session,
        )
        await async_session.commit()

        messages = await service.get_messages(
            user_id=sample_user.id,
            limit=10,
            db=async_session,
            hide_hitl_approvals=False,
        )

        # All messages should be returned
        assert len(messages) == 2


# ============================================================================
# get_audit_logs Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetAuditLogs:
    """Test get_audit_logs method."""

    async def test_returns_audit_logs(
        self, service, sample_user, sample_conversation, async_session
    ):
        """Test returns audit logs for user."""
        # Create audit log
        from src.domains.conversations.repository import ConversationRepository

        repo = ConversationRepository(async_session)
        await repo.create_audit_log(
            user_id=sample_user.id,
            conversation_id=sample_conversation.id,
            action="created",
            message_count_at_action=0,
            metadata={"test": "data"},
        )
        await async_session.commit()

        logs = await service.get_audit_logs(
            user_id=sample_user.id,
            db=async_session,
        )

        assert len(logs) >= 1
        assert any(log.action == "created" for log in logs)

    async def test_respects_limit(self, service, sample_user, async_session):
        """Test audit logs respect limit parameter."""
        from src.domains.conversations.repository import ConversationRepository

        repo = ConversationRepository(async_session)

        # Create multiple audit logs
        for i in range(5):
            await repo.create_audit_log(
                user_id=sample_user.id,
                conversation_id=sample_user.id,
                action=f"action_{i}",
                message_count_at_action=i,
                metadata={},
            )
        await async_session.commit()

        logs = await service.get_audit_logs(
            user_id=sample_user.id,
            db=async_session,
            limit=2,
        )

        assert len(logs) == 2


# ============================================================================
# get_messages_with_tokens Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetMessagesWithTokens:
    """Test get_messages_with_tokens method."""

    async def test_returns_empty_for_no_conversation(self, service, sample_user, async_session):
        """Test returns empty list when no conversation exists."""
        messages = await service.get_messages_with_tokens(
            user_id=sample_user.id,
            limit=50,
            db=async_session,
        )

        assert len(messages) == 0

    async def test_enriches_messages_with_token_data(
        self, service, sample_user, sample_conversation, async_session
    ):
        """Test messages enriched with token data."""
        run_id = "test-run-123"

        # Create message with run_id
        await service.archive_message(
            conversation_id=sample_conversation.id,
            role="assistant",
            content="Response",
            metadata={"run_id": run_id},
            db=async_session,
        )

        # Create token summary
        token_summary = MessageTokenSummary(
            user_id=sample_user.id,
            session_id=f"session_{sample_conversation.id}",
            run_id=run_id,
            conversation_id=sample_conversation.id,
            total_prompt_tokens=100,
            total_completion_tokens=50,
            total_cached_tokens=20,
            total_cost_eur=Decimal("0.05"),
        )
        async_session.add(token_summary)
        await async_session.commit()

        messages = await service.get_messages_with_tokens(
            user_id=sample_user.id,
            limit=10,
            db=async_session,
        )

        assert len(messages) == 1
        assert messages[0]["tokens_in"] == 100
        assert messages[0]["tokens_out"] == 50
        assert messages[0]["tokens_cache"] == 20

    async def test_handles_messages_without_tokens(
        self, service, sample_user, sample_conversation, async_session
    ):
        """Test handles messages without token data gracefully."""
        # Create message without run_id
        await service.archive_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="Query",
            metadata=None,
            db=async_session,
        )
        await async_session.commit()

        messages = await service.get_messages_with_tokens(
            user_id=sample_user.id,
            limit=10,
            db=async_session,
        )

        assert len(messages) == 1
        assert messages[0]["tokens_in"] is None
        assert messages[0]["tokens_out"] is None
        assert messages[0]["cost_eur"] is None


# ============================================================================
# get_messages_with_tokens_v2 Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetMessagesWithTokensV2:
    """Test get_messages_with_tokens_v2 (optimized) method."""

    async def test_returns_empty_for_no_conversation(self, service, sample_user, async_session):
        """Test returns empty list when no conversation exists."""
        messages = await service.get_messages_with_tokens_v2(
            user_id=sample_user.id,
            limit=50,
            db=async_session,
        )

        assert len(messages) == 0

    async def test_uses_optimized_query(
        self, service, sample_user, sample_conversation, async_session
    ):
        """Test uses optimized LEFT JOIN query."""
        run_id = "test-run-456"

        # Create message
        await service.archive_message(
            conversation_id=sample_conversation.id,
            role="assistant",
            content="Response",
            metadata={"run_id": run_id},
            db=async_session,
        )

        # Create token summary
        token_summary = MessageTokenSummary(
            user_id=sample_user.id,
            session_id=f"session_{sample_conversation.id}",
            run_id=run_id,
            conversation_id=sample_conversation.id,
            total_prompt_tokens=200,
            total_completion_tokens=100,
            total_cached_tokens=30,
            total_cost_eur=Decimal("0.10"),
        )
        async_session.add(token_summary)
        await async_session.commit()

        messages = await service.get_messages_with_tokens_v2(
            user_id=sample_user.id,
            limit=10,
            db=async_session,
        )

        assert len(messages) == 1
        assert messages[0]["tokens_in"] == 200
        assert messages[0]["tokens_out"] == 100


# ============================================================================
# get_messages_with_tokens_auto Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetMessagesWithTokensAuto:
    """Test get_messages_with_tokens_auto always uses v2 implementation.

    Note: The USE_CONVERSATION_REPOSITORY feature flag was removed.
    get_messages_with_tokens_auto now always uses the optimized v2 implementation.
    """

    async def test_always_uses_v2_implementation(
        self, service, sample_user, sample_conversation, async_session
    ):
        """Test that get_messages_with_tokens_auto always uses v2."""
        # Create message
        await service.archive_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="Test",
            metadata=None,
            db=async_session,
        )
        await async_session.commit()

        messages = await service.get_messages_with_tokens_auto(
            user_id=sample_user.id,
            limit=10,
            db=async_session,
        )

        # Should use v2 (optimized) - always now
        assert isinstance(messages, list)


# ============================================================================
# get_conversation_totals Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetConversationTotals:
    """Test get_conversation_totals method."""

    async def test_returns_zero_for_no_conversation(self, service, sample_user, async_session):
        """Test returns zeros when no conversation exists."""
        totals = await service.get_conversation_totals(
            user_id=sample_user.id,
            db=async_session,
        )

        assert totals["conversation_id"] is None
        assert totals["total_tokens_in"] == 0
        assert totals["total_tokens_out"] == 0
        assert totals["total_cost_eur"] == 0.0

    @patch("src.domains.conversations.service.ConversationRepository")
    async def test_calculates_totals(
        self,
        mock_repo_class,
        service,
        sample_user,
        sample_conversation,
        async_session,
    ):
        """Test calculates conversation totals with mocking."""
        # Mock repository
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        # Mock token totals response
        # Repository returns standardized keys matching field_names constants
        mock_repo.get_token_totals.return_value = {
            FIELD_TOTAL_TOKENS_IN: 300,
            FIELD_TOTAL_TOKENS_OUT: 150,
            FIELD_TOTAL_TOKENS_CACHE: 30,
            FIELD_TOTAL_COST_EUR: 0.0025,  # Historical cost from message_token_summary
        }

        # Execute - service uses aggregated totals directly (O(1) optimization)
        totals = await service.get_conversation_totals(
            user_id=sample_user.id,
            db=async_session,
        )

        # Verify totals are calculated from repository response
        assert totals[FIELD_TOTAL_TOKENS_IN] == 300
        assert totals[FIELD_TOTAL_TOKENS_OUT] == 150
        assert totals[FIELD_TOTAL_TOKENS_CACHE] == 30
        # Cost comes directly from aggregated historical cost
        assert totals[FIELD_TOTAL_COST_EUR] == 0.0025


# ============================================================================
# reset_conversation Tests (with mocking)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestResetConversation:
    """Test reset_conversation with proper mocking."""

    @patch("src.domains.conversations.checkpointer.get_checkpointer")
    @patch("src.domains.agents.context.manager.ToolContextManager")
    @patch("src.domains.agents.context.store.get_tool_context_store")
    @patch("src.infrastructure.cache.redis.get_redis_cache")
    async def test_resets_conversation_stats(
        self,
        mock_redis,
        mock_context_store,
        mock_context_manager_class,
        mock_checkpointer,
        service,
        sample_user,
        sample_conversation,
        async_session,
    ):
        """Test reset clears stats and messages."""
        # Setup mocks
        mock_checkpointer_instance = AsyncMock()
        mock_checkpointer_instance.adelete_thread = AsyncMock()
        mock_checkpointer.return_value = mock_checkpointer_instance

        mock_context_manager = AsyncMock()
        mock_context_manager.cleanup_session_contexts = AsyncMock(
            return_value={"domains_cleaned": [], "total_items_deleted": 0}
        )
        mock_context_manager_class.return_value = mock_context_manager

        mock_store_instance = AsyncMock()
        mock_context_store.return_value = mock_store_instance

        mock_redis_instance = AsyncMock()
        mock_redis_instance.delete = AsyncMock(return_value=0)
        mock_redis_instance.scan = AsyncMock(return_value=(0, []))
        mock_redis.return_value = mock_redis_instance

        # Set initial stats
        sample_conversation.message_count = 10
        sample_conversation.total_tokens = 5000
        await async_session.commit()

        # Create a message
        await service.archive_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="Test message",
            metadata=None,
            db=async_session,
        )
        await async_session.commit()

        # Reset conversation
        await service.reset_conversation(
            user_id=sample_user.id,
            db=async_session,
        )

        # Verify reset
        await async_session.refresh(sample_conversation)
        assert sample_conversation.message_count == 0
        assert sample_conversation.total_tokens == 0

        # Verify checkpointer called
        mock_checkpointer_instance.adelete_thread.assert_called_once()

    @patch("src.domains.conversations.checkpointer.get_checkpointer")
    @patch("src.domains.agents.context.manager.ToolContextManager")
    @patch("src.domains.agents.context.store.get_tool_context_store")
    @patch("src.infrastructure.cache.redis.get_redis_cache")
    async def test_creates_audit_log_on_reset(
        self,
        mock_redis,
        mock_context_store,
        mock_context_manager_class,
        mock_checkpointer,
        service,
        sample_user,
        sample_conversation,
        async_session,
    ):
        """Test audit log created on reset."""
        # Setup mocks
        mock_checkpointer_instance = AsyncMock()
        mock_checkpointer_instance.adelete_thread = AsyncMock()
        mock_checkpointer.return_value = mock_checkpointer_instance

        mock_context_manager = AsyncMock()
        mock_context_manager.cleanup_session_contexts = AsyncMock(
            return_value={"domains_cleaned": [], "total_items_deleted": 0}
        )
        mock_context_manager_class.return_value = mock_context_manager

        mock_store_instance = AsyncMock()
        mock_context_store.return_value = mock_store_instance

        mock_redis_instance = AsyncMock()
        mock_redis_instance.delete = AsyncMock(return_value=0)
        mock_redis_instance.scan = AsyncMock(return_value=(0, []))
        mock_redis.return_value = mock_redis_instance

        sample_conversation.message_count = 5
        sample_conversation.total_tokens = 1000
        await async_session.commit()

        await service.reset_conversation(
            user_id=sample_user.id,
            db=async_session,
        )

        # Verify audit log
        from sqlalchemy import select

        stmt = select(ConversationAuditLog).where(
            ConversationAuditLog.conversation_id == sample_conversation.id,
            ConversationAuditLog.action == "reset",
        )
        result = await async_session.execute(stmt)
        audit_log = result.scalar_one_or_none()

        assert audit_log is not None
        assert audit_log.action == "reset"
        assert audit_log.message_count_at_action == 5

    async def test_reset_handles_no_conversation(self, service, sample_user, async_session):
        """Test reset handles missing conversation gracefully."""
        # Should not raise exception
        await service.reset_conversation(
            user_id=sample_user.id,
            db=async_session,
        )


# ============================================================================
# _generate_title Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGenerateTitle:
    """Test _generate_title method."""

    def test_generates_title_with_date(self, service):
        """Test generates title with current date."""
        title = service._generate_title()

        assert "Conversation du" in title
        # Should contain date in DD/MM/YYYY format
        import re

        assert re.search(r"\d{2}/\d{2}/\d{4}", title)

    def test_generates_unique_titles_on_different_days(self, service):
        """Test titles reflect current date."""
        with patch("src.domains.conversations.service.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 1, 15, tzinfo=UTC)
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            title = service._generate_title()
            assert "15/01/2024" in title
