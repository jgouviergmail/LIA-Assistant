"""Integration tests for the ``search`` parameter of ConversationRepository.

Validates the filtering contract of ``get_messages_with_token_summaries(...,
search=...)`` used by ``GET /conversations/me/messages?search=``:

- case-insensitive (ILIKE),
- **accent-insensitive** (``unaccent()`` on both sides — QW-2, aligned with the
  admin user search; the extension is installed by migration
  ``add_unaccent_ext_001``),
- LIKE wildcards (``%``, ``_``) in the user's term are treated as literals.

These tests lock that contract — weakening any of the three dimensions must be
a conscious change.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.repository import ConversationRepository

# Repository search uses PostgreSQL ILIKE + unaccent — needs a real DB.
pytestmark = pytest.mark.integration


@pytest.fixture
async def user_with_messages(async_session: AsyncSession):
    """Create a user + conversation + 6 messages with varied content."""
    from src.domains.users.models import User

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
        "Remise de 50% appliquée",  # literal % (wildcard-escaping contract)
    ]
    for role_content in zip(
        ["user", "assistant", "user", "assistant", "user", "assistant"],
        contents,
        strict=True,
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

        assert len(results) == 6

    @pytest.mark.asyncio
    async def test_search_accent_insensitive_both_directions(
        self, async_session: AsyncSession, user_with_messages
    ):
        """QW-2 contract: 'reunion' matches 'réunion' and vice versa.

        ``unaccent()`` is applied to both the column and the pattern, so the
        accented and unaccented spellings are equivalent in both directions —
        same behaviour the FAQ search already has client-side.
        """
        _, conversation = user_with_messages
        repo = ConversationRepository(async_session)

        expected = {
            "Note un rendez-vous pour la réunion",
            "Prepare the reunion agenda",
        }

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

        assert {msg.content for msg, _ in without_accent} == expected
        assert {msg.content for msg, _ in with_accent} == expected

    @pytest.mark.asyncio
    async def test_search_treats_like_wildcards_as_literals(
        self, async_session: AsyncSession, user_with_messages
    ):
        """'%' and '_' in the user's term are literals, never LIKE wildcards.

        Unescaped, '50%' would match any content containing '50' followed by
        anything; escaped, it only matches the literal string '50%'.
        """
        _, conversation = user_with_messages
        repo = ConversationRepository(async_session)

        percent = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id,
            limit=50,
            search="50%",
        )
        assert {msg.content for msg, _ in percent} == {"Remise de 50% appliquée"}

        # A bare wildcard must not match everything — no literal '%'-free row
        # contains an underscore, so '_a' only matches nothing (not "any char
        # followed by a").
        underscore = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id,
            limit=50,
            search="_izza",
        )
        assert underscore == []
