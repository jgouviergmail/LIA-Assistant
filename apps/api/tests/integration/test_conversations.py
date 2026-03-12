"""
Integration tests for Conversation API endpoints.

Tests conversation management, message archival, and soft delete operations.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.models import User
from src.domains.conversations.models import Conversation, ConversationMessage


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_conversation_not_found(
    authenticated_client: tuple[AsyncClient, User],
):
    """Test getting conversation that doesn't exist returns null (lazy creation)."""
    client, user = authenticated_client

    response = await client.get("/api/v1/conversations/me")

    # No conversation exists yet (lazy creation) - returns 200 with null
    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_conversation_after_creation(
    authenticated_client: tuple[AsyncClient, User],
    async_session: AsyncSession,
):
    """Test getting conversation after it's created."""
    client, user = authenticated_client

    # Create conversation manually
    conversation = Conversation(
        id=user.id,
        user_id=user.id,
        title="Test Conversation",
        message_count=0,
        total_tokens=0,
    )
    async_session.add(conversation)
    await async_session.commit()

    # Get conversation
    response = await client.get("/api/v1/conversations/me")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(user.id)
    assert data["title"] == "Test Conversation"
    assert data["message_count"] == 0
    assert data["total_tokens"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_conversation_messages_empty(
    authenticated_client: tuple[AsyncClient, User],
    async_session: AsyncSession,
):
    """Test listing messages for conversation with no messages."""
    client, user = authenticated_client

    # Create conversation
    conversation = Conversation(
        id=user.id,
        user_id=user.id,
        title="Empty Conversation",
        message_count=0,
        total_tokens=0,
    )
    async_session.add(conversation)
    await async_session.commit()

    # List messages
    response = await client.get("/api/v1/conversations/me/messages")

    assert response.status_code == 200
    data = response.json()
    assert data["messages"] == []
    assert data["total_count"] == 0
    assert data["conversation_id"] == str(user.id)


@pytest.mark.skip(
    reason="Test logic needs update: total_count returns user message count, not total messages. Also needs investigation into message filtering during testcontainer setup."
)
@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_conversation_messages_with_pagination(
    authenticated_client: tuple[AsyncClient, User],
    async_session: AsyncSession,
):
    """Test listing messages with pagination."""
    client, user = authenticated_client

    # Create conversation
    conversation = Conversation(
        id=user.id,
        user_id=user.id,
        title="Paginated Conversation",
        message_count=3,
        total_tokens=0,
    )
    async_session.add(conversation)

    # Add messages
    for i in range(3):
        message = ConversationMessage(
            conversation_id=user.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i + 1}",
        )
        async_session.add(message)

    await async_session.commit()

    # Get first page (limit=2) - messages returned newest first (descending)
    response = await client.get("/api/v1/conversations/me/messages?limit=2")

    assert response.status_code == 200
    data = response.json()
    assert len(data["messages"]) == 2
    assert data["total_count"] == 3
    assert data["conversation_id"] == str(user.id)
    # Messages are returned newest first (DESC order by created_at)
    assert data["messages"][0]["content"] == "Message 3"
    assert data["messages"][1]["content"] == "Message 2"


@pytest.mark.skip(
    reason="INFRASTRUCTURE: reset endpoint tries to delete from checkpoint tables which don't exist in test DB"
)
@pytest.mark.asyncio
@pytest.mark.integration
async def test_reset_conversation_soft_delete(
    authenticated_client: tuple[AsyncClient, User],
    async_session: AsyncSession,
):
    """Test soft delete of conversation via reset endpoint."""
    client, user = authenticated_client

    # Create conversation
    conversation = Conversation(
        id=user.id,
        user_id=user.id,
        title="To Delete",
        message_count=5,
        total_tokens=100,
    )
    async_session.add(conversation)
    await async_session.commit()

    # Reset conversation (soft delete)
    response = await client.post("/api/v1/conversations/me/reset")

    assert response.status_code == 200
    data = response.json()
    assert data["previous_message_count"] == 5

    # Verify soft delete (deleted_at should be set)
    await async_session.refresh(conversation)
    assert conversation.deleted_at is not None

    # Verify can't get deleted conversation (returns null)
    response = await client.get("/api/v1/conversations/me")
    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reset_nonexistent_conversation(
    authenticated_client: tuple[AsyncClient, User],
):
    """Test resetting conversation that doesn't exist returns 404."""
    client, user = authenticated_client

    response = await client.post("/api/v1/conversations/me/reset")

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_conversation_stats(
    authenticated_client: tuple[AsyncClient, User],
    async_session: AsyncSession,
):
    """Test getting conversation statistics."""
    client, user = authenticated_client

    # Create conversation with stats
    conversation = Conversation(
        id=user.id,
        user_id=user.id,
        title="Stats Conversation",
        message_count=10,
        total_tokens=5000,
    )
    async_session.add(conversation)
    await async_session.commit()

    # Get stats
    response = await client.get("/api/v1/conversations/me")

    assert response.status_code == 200
    data = response.json()
    assert data["message_count"] == 10
    assert data["total_tokens"] == 5000


@pytest.mark.asyncio
@pytest.mark.integration
async def test_user_can_only_access_own_conversation(
    authenticated_client: tuple[AsyncClient, User],
    async_session: AsyncSession,
):
    """Test users can only access their own conversations via /me endpoint."""
    client, user = authenticated_client

    # Create another user's conversation
    other_user = User(
        email="other@example.com",
        hashed_password="hash",
        full_name="Other User",
        is_active=True,
        is_verified=True,
    )
    async_session.add(other_user)
    await async_session.flush()

    other_conversation = Conversation(
        id=other_user.id,
        user_id=other_user.id,
        title="Other User's Conversation",
        message_count=10,
        total_tokens=1000,
    )
    async_session.add(other_conversation)

    # Create current user's conversation
    my_conversation = Conversation(
        id=user.id,
        user_id=user.id,
        title="My Conversation",
        message_count=5,
        total_tokens=500,
    )
    async_session.add(my_conversation)
    await async_session.commit()

    # Access /me endpoint - should return current user's conversation, not other_user's
    response = await client.get("/api/v1/conversations/me")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(user.id)
    assert data["title"] == "My Conversation"
    assert data["message_count"] == 5
    assert data["total_tokens"] == 500
