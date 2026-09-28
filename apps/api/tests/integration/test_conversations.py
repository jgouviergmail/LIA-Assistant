"""
Integration tests for Conversation API endpoints.

Tests conversation management, message archival, and soft delete operations.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.attachments.models import (
    Attachment,
    AttachmentContentType,
    AttachmentOrigin,
    AttachmentStatus,
)
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.users.models import User


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


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_conversation_messages_with_pagination(
    authenticated_client: tuple[AsyncClient, User],
    async_session: AsyncSession,
):
    """Test listing messages with pagination (current contract).

    ``total_count`` is NOT a global message total: it counts the USER messages
    of the RETURNED PAGE (router: ``total_user_messages`` — "semantics
    preserved for backwards compatibility; not a global total"). With three
    messages (user/assistant/user) and ``limit=2``, the newest-first page is
    [Message 3 (user), Message 2 (assistant)] → ``total_count == 1``.
    """
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
    assert data["conversation_id"] == str(user.id)
    # Messages are returned newest first (DESC order by created_at)
    assert data["messages"][0]["content"] == "Message 3"
    assert data["messages"][1]["content"] == "Message 2"
    # Page-scoped USER-message count: only "Message 3" is role=user here.
    assert data["total_count"] == 1
    # Pagination contract: one older message remains.
    assert data["has_more"] is True
    assert data["next_cursor"] is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_history_restates_each_file_card_from_its_row(
    authenticated_client: tuple[AsyncClient, User],
    async_session: AsyncSession,
):
    """A file card states the lifetime its file has NOW, not the one it was written with.

    The cards were written when the files were produced; since then one file
    was KEPT (no deadline, ADR-319), one still has a (new) deadline, and one was
    deleted. The history read path restates every card from its attachment row
    and never rewrites the stored metadata.
    """
    client, user = authenticated_client
    written = "2026-01-01T00:00:00+00:00"
    current = datetime.now(UTC) + timedelta(hours=5)

    def generated(origin: AttachmentOrigin, expires_at: datetime | None) -> Attachment:
        stored = f"{uuid4()}.bin"
        return Attachment(
            user_id=user.id,
            original_filename=f"generated_{stored}",
            stored_filename=stored,
            mime_type="image/png",
            file_size=10,
            file_path=f"{user.id}/{stored}",
            content_type=AttachmentContentType.IMAGE,
            origin=origin.value,
            status=AttachmentStatus.READY,
            expires_at=expires_at,
        )

    kept = generated(AttachmentOrigin.GENERATED_IMAGE, None)
    live = generated(AttachmentOrigin.GENERATED_DOCUMENT, current)
    async_session.add_all([kept, live])
    async_session.add(
        Conversation(id=user.id, user_id=user.id, title="Cards", message_count=1, total_tokens=0)
    )
    await async_session.flush()
    message = ConversationMessage(
        conversation_id=user.id,
        role="assistant",
        content="Here they are.",
        message_metadata={
            "generated_images": [
                {"url": f"/api/v1/attachments/{kept.id}", "alt": "kept", "expires_at": written},
                {"url": f"/api/v1/attachments/{uuid4()}", "alt": "gone", "expires_at": written},
            ],
            "generated_documents": [
                {
                    "url": f"/api/v1/attachments/{live.id}",
                    "filename": "report.md",
                    "doc_type": "md",
                    "size_bytes": 10,
                    "expires_at": written,
                }
            ],
        },
    )
    async_session.add(message)
    await async_session.commit()

    response = await client.get("/api/v1/conversations/me/messages")

    assert response.status_code == 200
    metadata = response.json()["messages"][0]["message_metadata"]
    kept_card, gone_card = metadata["generated_images"]
    assert kept_card["kept"] is True and kept_card["expires_at"] is None
    assert gone_card["gone"] is True
    document = metadata["generated_documents"][0]
    assert document["kept"] is False and document["gone"] is False
    assert datetime.fromisoformat(document["expires_at"]) == current
    # What the history shows is a reading, never a rewrite of the record.
    stored = await async_session.scalar(
        select(ConversationMessage.message_metadata).where(ConversationMessage.id == message.id)
    )
    assert stored is not None
    assert stored["generated_images"][0] == {
        "url": f"/api/v1/attachments/{kept.id}",
        "alt": "kept",
        "expires_at": written,
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reset_conversation_preserves_record_and_purges(
    authenticated_client: tuple[AsyncClient, User],
    async_session: AsyncSession,
):
    """Reset endpoint (current contract): purge + counters to zero, NO soft delete.

    ``reset_conversation`` deliberately does NOT set ``deleted_at`` (it would
    hit the id=user_id unique constraint on recreation — see the service
    docstring): the conversation record survives with its counters reset and
    its messages purged, and GET /me keeps returning it.
    """
    client, user = authenticated_client

    # Create conversation with one real message to prove the purge.
    conversation = Conversation(
        id=user.id,
        user_id=user.id,
        title="To Reset",
        message_count=5,
        total_tokens=100,
    )
    async_session.add(conversation)
    async_session.add(
        ConversationMessage(conversation_id=user.id, role="user", content="Before reset")
    )
    await async_session.commit()

    response = await client.post("/api/v1/conversations/me/reset")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["previous_message_count"] == 5

    # The conversation record SURVIVES (no soft delete), counters reset.
    await async_session.refresh(conversation)
    assert conversation.deleted_at is None
    assert conversation.message_count == 0
    assert conversation.total_tokens == 0

    # Messages are purged.
    result = await async_session.execute(
        select(ConversationMessage).where(ConversationMessage.conversation_id == user.id)
    )
    assert list(result.scalars().all()) == []

    # GET /me still returns the (reset) conversation, not null.
    response = await client.get("/api/v1/conversations/me")
    assert response.status_code == 200
    body = response.json()
    assert body is not None
    assert body["message_count"] == 0


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
