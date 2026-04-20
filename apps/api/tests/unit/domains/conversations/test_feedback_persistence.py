"""Unit tests for ConversationRepository.mark_interest_feedback_submitted.

Validates that interest feedback submission is persisted on every proactive
message that references the interest via ``message_metadata.target_id``, and
that cross-tenant writes are prevented by the ``user_id`` filter.

Uses testcontainers/real DB because the method relies on PostgreSQL JSONB
functions (``jsonb_set``, ``coalesce``, ``to_jsonb``) that cannot be exercised
against an in-memory SQLite.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.field_names import (
    FIELD_FEEDBACK_SUBMITTED,
    FIELD_FEEDBACK_VALUE,
    FIELD_TARGET_ID,
)
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.repository import ConversationRepository

# Skip in pre-commit: requires Postgres (JSONB functions).
pytestmark = pytest.mark.integration


@pytest.fixture
async def two_users(async_session: AsyncSession):
    """Create two independent users (used for cross-tenant isolation checks)."""
    from src.domains.auth.models import User

    user_a = User(
        email="user_a@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
    )
    user_b = User(
        email="user_b@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
    )
    async_session.add_all([user_a, user_b])
    await async_session.commit()
    await async_session.refresh(user_a)
    await async_session.refresh(user_b)
    return user_a, user_b


@pytest.fixture
async def conversations(async_session: AsyncSession, two_users):
    """Create one conversation per user."""
    user_a, user_b = two_users
    conv_a = Conversation(
        id=user_a.id, user_id=user_a.id, title="A", message_count=0, total_tokens=0
    )
    conv_b = Conversation(
        id=user_b.id, user_id=user_b.id, title="B", message_count=0, total_tokens=0
    )
    async_session.add_all([conv_a, conv_b])
    await async_session.commit()
    await async_session.refresh(conv_a)
    await async_session.refresh(conv_b)
    return conv_a, conv_b


class TestMarkInterestFeedbackSubmitted:
    """Test ConversationRepository.mark_interest_feedback_submitted."""

    @pytest.mark.asyncio
    async def test_marks_single_message(
        self, async_session: AsyncSession, two_users, conversations
    ):
        """GIVEN one proactive message referencing an interest,
        WHEN mark_interest_feedback_submitted is called for that user,
        THEN message_metadata is updated with feedback_submitted=true + value."""
        user_a, _ = two_users
        conv_a, _ = conversations
        interest_id = uuid4()

        msg = ConversationMessage(
            conversation_id=conv_a.id,
            role="assistant",
            content="Did you know...",
            message_metadata={
                FIELD_TARGET_ID: str(interest_id),
                "type": "proactive_interest",
            },
        )
        async_session.add(msg)
        await async_session.commit()
        await async_session.refresh(msg)

        repo = ConversationRepository(async_session)
        count = await repo.mark_interest_feedback_submitted(
            user_id=user_a.id,
            interest_id=interest_id,
            feedback_value="thumbs_up",
        )
        await async_session.commit()

        assert count == 1

        result = await async_session.execute(
            select(ConversationMessage).where(ConversationMessage.id == msg.id)
        )
        refreshed = result.scalar_one()
        assert refreshed.message_metadata is not None
        assert refreshed.message_metadata[FIELD_FEEDBACK_SUBMITTED] is True
        assert refreshed.message_metadata[FIELD_FEEDBACK_VALUE] == "thumbs_up"
        # Pre-existing keys must be preserved
        assert refreshed.message_metadata[FIELD_TARGET_ID] == str(interest_id)
        assert refreshed.message_metadata["type"] == "proactive_interest"

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation(
        self, async_session: AsyncSession, two_users, conversations
    ):
        """GIVEN two users each with a proactive message for the SAME interest_id,
        WHEN mark_interest_feedback_submitted is called for user A,
        THEN only user A's message is updated — user B's remains untouched."""
        user_a, user_b = two_users
        conv_a, conv_b = conversations
        interest_id = uuid4()

        msg_a = ConversationMessage(
            conversation_id=conv_a.id,
            role="assistant",
            content="A's message",
            message_metadata={FIELD_TARGET_ID: str(interest_id)},
        )
        msg_b = ConversationMessage(
            conversation_id=conv_b.id,
            role="assistant",
            content="B's message",
            message_metadata={FIELD_TARGET_ID: str(interest_id)},
        )
        async_session.add_all([msg_a, msg_b])
        await async_session.commit()
        await async_session.refresh(msg_a)
        await async_session.refresh(msg_b)

        repo = ConversationRepository(async_session)
        count = await repo.mark_interest_feedback_submitted(
            user_id=user_a.id,
            interest_id=interest_id,
            feedback_value="block",
        )
        await async_session.commit()

        assert count == 1  # Only user A's message touched

        # user B's message must be untouched
        result = await async_session.execute(
            select(ConversationMessage).where(ConversationMessage.id == msg_b.id)
        )
        refreshed_b = result.scalar_one()
        assert FIELD_FEEDBACK_SUBMITTED not in (refreshed_b.message_metadata or {})

    @pytest.mark.asyncio
    async def test_null_metadata_handled_via_coalesce(
        self, async_session: AsyncSession, two_users, conversations
    ):
        """GIVEN a message with NULL message_metadata (legacy),
        WHEN mark_interest_feedback_submitted targets it via a matching interest_id,
        THEN no crash occurs AND 0 rows are affected (NULL metadata has no target_id)."""
        user_a, _ = two_users
        conv_a, _ = conversations
        interest_id = uuid4()

        msg = ConversationMessage(
            conversation_id=conv_a.id,
            role="assistant",
            content="Legacy null metadata",
            message_metadata=None,
        )
        async_session.add(msg)
        await async_session.commit()

        repo = ConversationRepository(async_session)
        count = await repo.mark_interest_feedback_submitted(
            user_id=user_a.id,
            interest_id=interest_id,
            feedback_value="thumbs_up",
        )
        await async_session.commit()

        # NULL metadata can't match target_id so no rows updated
        assert count == 0

    @pytest.mark.asyncio
    async def test_multiple_matching_messages(
        self, async_session: AsyncSession, two_users, conversations
    ):
        """GIVEN several proactive messages sharing the same interest_id,
        WHEN mark_interest_feedback_submitted is called,
        THEN all matching messages are updated (count == N)."""
        user_a, _ = two_users
        conv_a, _ = conversations
        interest_id = uuid4()

        messages = [
            ConversationMessage(
                conversation_id=conv_a.id,
                role="assistant",
                content=f"Proactive #{i}",
                message_metadata={FIELD_TARGET_ID: str(interest_id)},
            )
            for i in range(3)
        ]
        async_session.add_all(messages)
        await async_session.commit()

        repo = ConversationRepository(async_session)
        count = await repo.mark_interest_feedback_submitted(
            user_id=user_a.id,
            interest_id=interest_id,
            feedback_value="thumbs_down",
        )
        await async_session.commit()

        assert count == 3

    @pytest.mark.asyncio
    async def test_no_matching_messages(
        self, async_session: AsyncSession, two_users, conversations
    ):
        """GIVEN no messages referencing the interest_id,
        WHEN mark_interest_feedback_submitted is called,
        THEN 0 rows are affected (no error)."""
        user_a, _ = two_users

        repo = ConversationRepository(async_session)
        count = await repo.mark_interest_feedback_submitted(
            user_id=user_a.id,
            interest_id=uuid4(),
            feedback_value="thumbs_up",
        )
        await async_session.commit()

        assert count == 0
