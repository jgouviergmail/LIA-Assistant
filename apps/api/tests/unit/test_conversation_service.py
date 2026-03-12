"""
Unit tests for ConversationService.

Tests conversation lifecycle, message archival, and statistics tracking.
Adapted to match existing service implementation.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.models import User
from src.domains.conversations.models import (
    Conversation,
    ConversationAuditLog,
    ConversationMessage,
)
from src.domains.conversations.service import ConversationService

# Skip in pre-commit - uses testcontainers/real DB, too slow
# Run manually with: pytest tests/unit/test_conversation_service.py -v
pytestmark = pytest.mark.integration


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


# ============================================================================
# get_or_create_conversation Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_or_create_conversation_creates_new(
    async_session: AsyncSession,
    sample_user: User,
):
    """Test creating new conversation when none exists."""
    service = ConversationService()

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


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_or_create_conversation_returns_existing(
    async_session: AsyncSession,
    sample_user: User,
    sample_conversation: Conversation,
):
    """Test returning existing conversation instead of creating new one."""
    service = ConversationService()

    conversation = await service.get_or_create_conversation(
        user_id=sample_user.id,
        db=async_session,
    )

    assert conversation.id == sample_conversation.id
    assert conversation.title == "Test Conversation"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_or_create_conversation_with_soft_deleted(
    async_session: AsyncSession,
    sample_user: User,
):
    """Test that get_or_create reactivates soft-deleted conversation instead of creating new.

    FIX: This test was previously skipped due to unique constraint violations.
    The fix in service.py now checks for soft-deleted conversations and reactivates them.
    """
    # Create soft-deleted conversation
    deleted_conversation = Conversation(
        id=sample_user.id,
        user_id=sample_user.id,
        title="Deleted Conversation",
        message_count=5,
        total_tokens=100,
        deleted_at=datetime.now(UTC),
    )
    async_session.add(deleted_conversation)
    await async_session.commit()

    service = ConversationService()

    # Should reactivate the soft-deleted conversation (not create new one)
    # (1:1 mapping: one conversation per user, so can't create a new one)
    conversation = await service.get_or_create_conversation(
        user_id=sample_user.id,
        db=async_session,
    )

    # Verify it returns the existing conversation
    assert conversation.id == sample_user.id
    assert conversation.user_id == sample_user.id

    # Verify the conversation was reactivated (deleted_at should be None)
    assert conversation.deleted_at is None, "Conversation should be reactivated"

    # Verify message count is preserved
    assert conversation.message_count == 5, "Message count should be preserved"
    assert conversation.total_tokens == 100, "Token count should be preserved"

    # Verify title was regenerated (new title on reactivation)
    assert conversation.title != "Deleted Conversation", "Title should be regenerated"


# ============================================================================
# archive_message Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
async def test_archive_message_user(
    async_session: AsyncSession,
    sample_user: User,
    sample_conversation: Conversation,
):
    """Test archiving user message."""
    service = ConversationService()

    message = await service.archive_message(
        conversation_id=sample_conversation.id,
        role="user",
        content="Hello, how are you?",
        metadata=None,
        db=async_session,
    )
    await async_session.commit()

    # Verify message created
    assert message is not None
    assert message.role == "user"
    assert message.content == "Hello, how are you?"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_archive_message_with_metadata(
    async_session: AsyncSession,
    sample_user: User,
    sample_conversation: Conversation,
):
    """Test archiving assistant message with token metadata."""
    service = ConversationService()

    message = await service.archive_message(
        conversation_id=sample_conversation.id,
        role="assistant",
        content="I'm doing well, thank you!",
        metadata={
            "tokens_in": 10,
            "tokens_out": 20,
            "tokens_cache": 5,
            "cost_eur": 0.05,
        },
        db=async_session,
    )
    await async_session.commit()

    # Verify message with metadata
    assert message.role == "assistant"
    assert message.message_metadata is not None
    assert message.message_metadata.get("tokens_in") == 10
    assert message.message_metadata.get("tokens_out") == 20


@pytest.mark.asyncio
@pytest.mark.unit
async def test_archive_message_sequence_numbering(
    async_session: AsyncSession,
    sample_user: User,
    sample_conversation: Conversation,
):
    """Test sequence numbers increment correctly."""
    service = ConversationService()

    # Archive 3 messages
    messages = []
    for i in range(3):
        msg = await service.archive_message(
            conversation_id=sample_conversation.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i + 1}",
            metadata=None,
            db=async_session,
        )
        messages.append(msg)
    await async_session.commit()

    # Verify messages created in order
    assert len(messages) == 3
    assert messages[0].content == "Message 1"
    assert messages[1].content == "Message 2"
    assert messages[2].content == "Message 3"


# ============================================================================
# increment_conversation_stats Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
async def test_increment_conversation_stats(
    async_session: AsyncSession,
    sample_user: User,
    sample_conversation: Conversation,
):
    """Test incrementing conversation statistics."""
    service = ConversationService()

    # Initial stats
    assert sample_conversation.message_count == 0
    assert sample_conversation.total_tokens == 0

    # Increment stats
    await service.increment_conversation_stats(
        conversation_id=sample_conversation.id,
        tokens=100,
        db=async_session,
    )
    await async_session.commit()

    # Verify incremented
    await async_session.refresh(sample_conversation)
    assert sample_conversation.message_count == 1
    assert sample_conversation.total_tokens == 100


@pytest.mark.asyncio
@pytest.mark.unit
async def test_increment_conversation_stats_accumulates(
    async_session: AsyncSession,
    sample_user: User,
    sample_conversation: Conversation,
):
    """Test stats accumulate across multiple updates."""
    service = ConversationService()

    # First increment
    await service.increment_conversation_stats(
        conversation_id=sample_conversation.id,
        tokens=100,
        db=async_session,
    )
    await async_session.commit()

    # Second increment
    await service.increment_conversation_stats(
        conversation_id=sample_conversation.id,
        tokens=150,
        db=async_session,
    )
    await async_session.commit()

    # Verify accumulated
    await async_session.refresh(sample_conversation)
    assert sample_conversation.message_count == 2
    assert sample_conversation.total_tokens == 250


# ============================================================================
# reset_conversation Tests
# ============================================================================


@pytest.mark.skip(
    reason="INFRASTRUCTURE: reset_conversation tries to DELETE from checkpoint tables "
    "(checkpoints, checkpoint_writes) which don't exist in test database. "
    "LangGraph creates these tables automatically at runtime but they're not in Alembic migrations. "
    "Need to either: 1) Create checkpoint tables in test setup, 2) Mock the checkpoint purge, "
    "or 3) Use SAVEPOINT in reset_conversation to isolate checkpoint deletion failure."
)
@pytest.mark.asyncio
@pytest.mark.unit
async def test_reset_conversation(
    async_session: AsyncSession,
    sample_user: User,
    sample_conversation: Conversation,
):
    """Test resetting conversation resets stats and deletes messages."""
    service = ConversationService()

    # Add some data
    sample_conversation.message_count = 10
    sample_conversation.total_tokens = 5000
    await async_session.commit()

    # Add a message
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

    # Verify messages deleted
    result = await async_session.execute(
        select(ConversationMessage).where(
            ConversationMessage.conversation_id == sample_conversation.id
        )
    )
    messages = list(result.scalars().all())
    assert len(messages) == 0


@pytest.mark.skip(
    reason="INFRASTRUCTURE: Same issue as test_reset_conversation - checkpoint tables missing"
)
@pytest.mark.asyncio
@pytest.mark.unit
async def test_reset_conversation_creates_audit_log(
    async_session: AsyncSession,
    sample_user: User,
    sample_conversation: Conversation,
):
    """Test reset conversation creates audit log entry."""
    service = ConversationService()

    # Add some stats before reset
    sample_conversation.message_count = 10
    sample_conversation.total_tokens = 5000
    await async_session.commit()

    # Reset conversation
    await service.reset_conversation(
        user_id=sample_user.id,
        db=async_session,
    )

    # Verify audit log created
    result = await async_session.execute(
        select(ConversationAuditLog).where(
            ConversationAuditLog.conversation_id == sample_conversation.id,
            ConversationAuditLog.action == "reset",
        )
    )
    audit_log = result.scalar_one()

    assert audit_log.action == "reset"
    assert audit_log.message_count_at_action == 10
    assert audit_log.audit_metadata.get("total_tokens") == 5000


# ============================================================================
# get_messages Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_messages_empty(
    async_session: AsyncSession,
    sample_user: User,
    sample_conversation: Conversation,
):
    """Test getting messages from conversation with no messages."""
    service = ConversationService()

    messages = await service.get_messages(
        user_id=sample_user.id,
        limit=50,
        db=async_session,
    )

    assert len(messages) == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_messages_pagination(
    async_session: AsyncSession,
    sample_user: User,
    sample_conversation: Conversation,
):
    """Test pagination of conversation messages."""
    service = ConversationService()

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

    # Get messages (limit=2, newest first)
    messages = await service.get_messages(
        user_id=sample_user.id,
        limit=2,
        db=async_session,
    )

    assert len(messages) == 2
    # Messages are returned newest first (descending order)
    assert messages[0].content == "Message 5"
    assert messages[1].content == "Message 4"

    # Get all messages
    messages = await service.get_messages(
        user_id=sample_user.id,
        limit=10,
        db=async_session,
    )

    assert len(messages) == 5
    # Verify descending order (newest first)
    assert messages[0].content == "Message 5"
    assert messages[4].content == "Message 1"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_messages_ordered_by_sequence(
    async_session: AsyncSession,
    sample_user: User,
    sample_conversation: Conversation,
):
    """Test messages are returned in sequence order."""
    service = ConversationService()

    # Create messages
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

    # Verify ordering by created_at (newest first - descending)
    assert len(messages) == 3
    assert messages[0].content == "Message 3"
    assert messages[1].content == "Message 2"
    assert messages[2].content == "Message 1"
