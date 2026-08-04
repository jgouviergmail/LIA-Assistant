"""Unit tests for ConversationRepository.mark_proactive_feedback_submitted.

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

# Requires Postgres (JSONB functions) — external via TEST_DATABASE_URL or Testcontainers.
pytestmark = pytest.mark.integration


@pytest.fixture
async def two_users(async_session: AsyncSession):
    """Create two independent users (used for cross-tenant isolation checks)."""
    from src.domains.users.models import User

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
    """Test ConversationRepository.mark_proactive_feedback_submitted."""

    @pytest.mark.asyncio
    async def test_marks_single_message(
        self, async_session: AsyncSession, two_users, conversations
    ):
        """GIVEN one proactive message referencing an interest,
        WHEN mark_proactive_feedback_submitted is called for that user,
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
        count = await repo.mark_proactive_feedback_submitted(
            user_id=user_a.id,
            target_id=interest_id,
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
        WHEN mark_proactive_feedback_submitted is called for user A,
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
        count = await repo.mark_proactive_feedback_submitted(
            user_id=user_a.id,
            target_id=interest_id,
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
        WHEN mark_proactive_feedback_submitted targets it via a matching interest_id,
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
        count = await repo.mark_proactive_feedback_submitted(
            user_id=user_a.id,
            target_id=interest_id,
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
        WHEN mark_proactive_feedback_submitted is called,
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
        count = await repo.mark_proactive_feedback_submitted(
            user_id=user_a.id,
            target_id=interest_id,
            feedback_value="thumbs_down",
        )
        await async_session.commit()

        assert count == 3

    @pytest.mark.asyncio
    async def test_no_matching_messages(
        self, async_session: AsyncSession, two_users, conversations
    ):
        """GIVEN no messages referencing the interest_id,
        WHEN mark_proactive_feedback_submitted is called,
        THEN 0 rows are affected (no error)."""
        user_a, _ = two_users

        repo = ConversationRepository(async_session)
        count = await repo.mark_proactive_feedback_submitted(
            user_id=user_a.id,
            target_id=uuid4(),
            feedback_value="thumbs_up",
        )
        await async_session.commit()

        assert count == 0


class TestARunIdScopesTheMarkToOneCard:
    """A verdict is about ONE notification, not about every past one.

    An interest card's ``target_id`` is the INTEREST, so marking by target_id
    alone locks every notification that interest ever produced. Measured on the
    development database on 2026-08-03: one interest carried NINE archived
    cards, several carried six. A single 👍 therefore disabled the buttons on
    eight other notifications while the audit trail recorded a verdict for only
    one of them — those eight would read "no feedback" in the history forever,
    with no way left for the reader to answer them.

    The card carries the notification's ``run_id``, which is exactly the
    granularity the audit trail uses (``update_feedback_by_run_id``). Passing it
    here makes both writes agree on what "this notification" means.

    Callers with no run_id (the settings list, older cards) keep the historical
    behaviour — see ``test_multiple_matching_messages`` above, which is the
    contract for that case and must keep passing.
    """

    @staticmethod
    def _card(conv_id, interest_id, run_id: str | None) -> ConversationMessage:
        metadata: dict[str, str] = {
            FIELD_TARGET_ID: str(interest_id),
            "type": "proactive_interest",
        }
        if run_id is not None:
            metadata["run_id"] = run_id
        return ConversationMessage(
            conversation_id=conv_id,
            role="assistant",
            content=f"card {run_id}",
            message_metadata=metadata,
        )

    @pytest.mark.asyncio
    async def test_only_the_voted_card_is_marked(
        self, async_session: AsyncSession, two_users, conversations
    ):
        """GIVEN three cards of the SAME interest, each with its own run_id,
        WHEN the verdict names one run_id,
        THEN exactly that card is marked and the other two stay answerable."""
        user_a, _ = two_users
        conv_a, _ = conversations
        interest_id = uuid4()

        cards = [self._card(conv_a.id, interest_id, f"proactive_interest_x_{i}") for i in range(3)]
        async_session.add_all(cards)
        await async_session.commit()
        for card in cards:
            await async_session.refresh(card)

        repo = ConversationRepository(async_session)
        count = await repo.mark_proactive_feedback_submitted(
            user_id=user_a.id,
            target_id=interest_id,
            feedback_value="thumbs_up",
            run_id="proactive_interest_x_1",
        )
        await async_session.commit()

        assert count == 1

        rows = (
            (
                await async_session.execute(
                    select(ConversationMessage).where(
                        ConversationMessage.id.in_([c.id for c in cards])
                    )
                )
            )
            .scalars()
            .all()
        )
        marked = {
            r.message_metadata["run_id"]
            for r in rows
            if (r.message_metadata or {}).get(FIELD_FEEDBACK_SUBMITTED) is True
        }
        assert marked == {"proactive_interest_x_1"}

    @pytest.mark.asyncio
    async def test_an_unknown_run_id_marks_nothing_rather_than_everything(
        self, async_session: AsyncSession, two_users, conversations
    ):
        """A run_id that matches nothing must NOT fall back to "all cards".

        The fallback would silently restore the very over-reach this closes.
        """
        user_a, _ = two_users
        conv_a, _ = conversations
        interest_id = uuid4()

        async_session.add_all([self._card(conv_a.id, interest_id, f"known_{i}") for i in range(2)])
        await async_session.commit()

        repo = ConversationRepository(async_session)
        count = await repo.mark_proactive_feedback_submitted(
            user_id=user_a.id,
            target_id=interest_id,
            feedback_value="block",
            run_id="never-emitted",
        )
        await async_session.commit()

        assert count == 0

    @pytest.mark.asyncio
    async def test_a_card_without_a_run_id_is_not_swept_in(
        self, async_session: AsyncSession, two_users, conversations
    ):
        """Cards archived before run_id travelled are not "the same" one.

        They keep their buttons rather than being marked by a verdict that was
        given elsewhere — an unanswerable card is worse than an open one.
        """
        user_a, _ = two_users
        conv_a, _ = conversations
        interest_id = uuid4()

        legacy = self._card(conv_a.id, interest_id, None)
        current = self._card(conv_a.id, interest_id, "proactive_interest_y_0")
        async_session.add_all([legacy, current])
        await async_session.commit()
        await async_session.refresh(legacy)

        repo = ConversationRepository(async_session)
        count = await repo.mark_proactive_feedback_submitted(
            user_id=user_a.id,
            target_id=interest_id,
            feedback_value="thumbs_down",
            run_id="proactive_interest_y_0",
        )
        await async_session.commit()

        assert count == 1
        refreshed = (
            await async_session.execute(
                select(ConversationMessage).where(ConversationMessage.id == legacy.id)
            )
        ).scalar_one()
        assert FIELD_FEEDBACK_SUBMITTED not in (refreshed.message_metadata or {})

    @pytest.mark.asyncio
    async def test_the_owner_filter_still_applies(
        self, async_session: AsyncSession, two_users, conversations
    ):
        """Narrowing by run_id must not replace the tenant scope.

        A run_id is not a secret; it travels in a client payload. Were it the
        only predicate, a forged one would reach another account's card.
        """
        user_a, user_b = two_users
        conv_a, conv_b = conversations
        interest_id = uuid4()
        shared_run_id = "proactive_interest_shared_0"

        mine = self._card(conv_a.id, interest_id, shared_run_id)
        theirs = self._card(conv_b.id, interest_id, shared_run_id)
        async_session.add_all([mine, theirs])
        await async_session.commit()
        await async_session.refresh(theirs)

        repo = ConversationRepository(async_session)
        count = await repo.mark_proactive_feedback_submitted(
            user_id=user_a.id,
            target_id=interest_id,
            feedback_value="thumbs_up",
            run_id=shared_run_id,
        )
        await async_session.commit()

        assert count == 1
        refreshed = (
            await async_session.execute(
                select(ConversationMessage).where(ConversationMessage.id == theirs.id)
            )
        ).scalar_one()
        assert FIELD_FEEDBACK_SUBMITTED not in (refreshed.message_metadata or {})
