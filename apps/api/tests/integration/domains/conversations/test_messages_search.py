"""Unit tests for the ``search`` parameter of ConversationRepository.

Validates case-insensitive ILIKE filtering on ``ConversationMessage.content``
when ``get_messages_with_token_summaries(..., search=...)`` is used by the
``GET /conversations/me/messages?search=`` endpoint.

MVP: accent-sensitive (``ILIKE`` without the ``unaccent`` extension). Tests
here lock that contract so a future switch to unaccent is a conscious change.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.repository import ConversationRepository

# Repository search uses PostgreSQL ILIKE — needs a real DB.
pytestmark = pytest.mark.integration


@pytest.fixture
async def user_with_messages(async_session: AsyncSession):
    """Create a user + conversation + 5 messages with varied content."""
    from src.domains.auth.models import User

    user = User(
        email="search_user@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    conversation = Conversation(
        id=user.id, user_id=user.id, title="S", message_count=0, total_tokens=0
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    contents = [
        "Peux-tu me rappeler la recette de la pizza",  # pizza + recette
        "J'adore la Pizza margherita",  # Pizza uppercase
        "Quelle est la météo demain",  # neither
        "Note un rendez-vous pour la réunion",  # réunion (with accent)
        "Prepare the reunion agenda",  # reunion (without accent)
    ]
    for role_content in zip(
        ["user", "assistant", "user", "assistant", "user"], contents, strict=True
    ):
        role, content = role_content
        async_session.add(
            ConversationMessage(
                conversation_id=conversation.id,
                role=role,
                content=content,
            )
        )
    await async_session.commit()

    return user, conversation


class TestMessagesSearch:
    """Exercises the ``search`` arg on get_messages_with_token_summaries."""

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, async_session: AsyncSession, user_with_messages):
        """ILIKE is case-insensitive: 'pizza' matches both lowercase and Pizza."""
        _, conversation = user_with_messages
        repo = ConversationRepository(async_session)

        results = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id,
            limit=50,
            search="pizza",
        )

        contents = [msg.content for msg, _ in results]
        assert len(contents) == 2
        assert any("pizza" in c.lower() for c in contents)

    @pytest.mark.asyncio
    async def test_search_no_match_returns_empty(
        self, async_session: AsyncSession, user_with_messages
    ):
        """When no message contains the substring, an empty list is returned."""
        _, conversation = user_with_messages
        repo = ConversationRepository(async_session)

        results = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id,
            limit=50,
            search="xyzzy_unlikely_token",
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_search_none_returns_all_messages(
        self, async_session: AsyncSession, user_with_messages
    ):
        """When ``search`` is None, no filtering is applied (preserve existing behaviour)."""
        _, conversation = user_with_messages
        repo = ConversationRepository(async_session)

        results = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id,
            limit=50,
            search=None,
        )

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_search_accent_sensitive_mvp_contract(
        self, async_session: AsyncSession, user_with_messages
    ):
        """MVP contract: ILIKE is accent-sensitive. 'reunion' does NOT match 'réunion'.

        This test documents the known MVP limitation. If the contract changes
        (e.g. pg_trgm/unaccent introduced), this test must be updated.
        """
        _, conversation = user_with_messages
        repo = ConversationRepository(async_session)

        without_accent = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id,
            limit=50,
            search="reunion",  # sans accent
        )
        with_accent = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id,
            limit=50,
            search="réunion",  # avec accent
        )

        reunion_contents = {msg.content for msg, _ in without_accent}
        reunion_accent_contents = {msg.content for msg, _ in with_accent}

        # Without accent: only matches the English "Prepare the reunion agenda"
        assert reunion_contents == {"Prepare the reunion agenda"}
        # With accent: only matches the French "Note un rendez-vous pour la réunion"
        assert reunion_accent_contents == {"Note un rendez-vous pour la réunion"}
