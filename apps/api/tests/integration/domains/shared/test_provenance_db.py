"""Bounded provenance, against a real database.

Three of the four properties here are PostgreSQL behaviours the unit tier
cannot reach — the CHECK that forbids a subject-less row, the ON DELETE SET
NULL that turns a reference into a tombstone, and the CASCADE that removes a
reference whose belief is gone.

The fourth is the promise the whole design rests on: **a deletion elsewhere is
never undone here**. Deleting the conversation must leave a dated row with no
text, not a remembered copy of what was said.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import PROVENANCE_MAX_REFERENCES_PER_SUBJECT
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.journals.models import JournalEntry
from src.domains.shared.provenance import ProvenanceOutcome, ProvenanceReference
from src.domains.shared.provenance_repository import ProvenanceRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def context(async_session: AsyncSession):
    """A user, a conversation, one turn in it, and a journal entry."""
    from src.domains.users.models import User

    user = User(email="prov@test.local", hashed_password="x", is_active=True, is_superuser=False)
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    conversation = Conversation(user_id=user.id, title="C", message_count=0, total_tokens=0)
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    message = ConversationMessage(
        conversation_id=conversation.id,
        role="user",
        content="Je préfère toujours un résumé écrit plutôt qu’un appel.",
    )
    entry = JournalEntry(
        user_id=user.id,
        theme="communication",
        title="Préfère l’écrit",
        content="Préfère un résumé écrit à un appel.",
        mood="neutral",
        status="active",
        source="conversation",
        char_count=42,
        level="L1",
        confidence="medium",
    )
    async_session.add_all([message, entry])
    await async_session.commit()
    await async_session.refresh(message)
    await async_session.refresh(entry)
    return user, conversation, message, entry


class TestTheReferenceIsBoundedAndScoped:
    async def test_it_stores_a_pointer_and_resolves_the_live_source(
        self, async_session: AsyncSession, context
    ):
        user, conversation, message, entry = context
        repo = ProvenanceRepository(async_session)

        await repo.record(
            user_id=user.id,
            journal_entry_id=entry.id,
            conversation_id=conversation.id,
            message_id=message.id,
        )
        await async_session.commit()

        [resolved] = await repo.resolve_for(user_id=user.id, journal_entry_id=entry.id)
        assert resolved.outcome == ProvenanceOutcome.ORIGIN.value
        assert resolved.conversation_id == conversation.id
        assert resolved.excerpt is not None
        assert "résumé écrit" in resolved.excerpt
        assert resolved.is_tombstone is False

    async def test_the_excerpt_is_read_live_and_never_stored(
        self, async_session: AsyncSession, context
    ):
        """Editing the turn changes what provenance shows — it holds no copy."""
        user, conversation, message, entry = context
        repo = ProvenanceRepository(async_session)
        await repo.record(
            user_id=user.id,
            journal_entry_id=entry.id,
            conversation_id=conversation.id,
            message_id=message.id,
        )
        await async_session.commit()

        message.content = "Finalement, appelle-moi."
        await async_session.commit()

        [resolved] = await repo.resolve_for(user_id=user.id, journal_entry_id=entry.id)
        assert resolved.excerpt == "Finalement, appelle-moi."

    async def test_it_keeps_only_the_most_recent_references(
        self, async_session: AsyncSession, context
    ):
        user, conversation, message, entry = context
        repo = ProvenanceRepository(async_session)
        base = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)

        for index in range(PROVENANCE_MAX_REFERENCES_PER_SUBJECT + 4):
            await repo.record(
                user_id=user.id,
                journal_entry_id=entry.id,
                conversation_id=conversation.id,
                message_id=message.id,
                outcome=ProvenanceOutcome.EVIDENCE,
                captured_at=base + timedelta(hours=index),
            )
        await async_session.commit()

        kept = await repo.resolve_for(user_id=user.id, journal_entry_id=entry.id)
        assert len(kept) == PROVENANCE_MAX_REFERENCES_PER_SUBJECT
        # The newest survived, the oldest went.
        assert kept[0].captured_at == base + timedelta(
            hours=PROVENANCE_MAX_REFERENCES_PER_SUBJECT + 3
        )

    async def test_another_account_resolves_nothing(self, async_session: AsyncSession, context):
        """A forged subject id must not read someone else's provenance."""
        user, conversation, message, entry = context
        repo = ProvenanceRepository(async_session)
        await repo.record(
            user_id=user.id,
            journal_entry_id=entry.id,
            conversation_id=conversation.id,
            message_id=message.id,
        )
        await async_session.commit()

        assert await repo.resolve_for(user_id=uuid.uuid4(), journal_entry_id=entry.id) == []

    async def test_a_row_without_a_subject_is_refused_by_the_database(
        self, async_session: AsyncSession, context
    ):
        """The CHECK is the guarantee — a convention would eventually be broken."""
        user, conversation, _message, _entry = context
        async_session.add(ProvenanceReference(user_id=user.id, conversation_id=conversation.id))

        with pytest.raises(IntegrityError):
            await async_session.commit()
        await async_session.rollback()

    async def test_a_row_with_two_subjects_is_refused_too(
        self, async_session: AsyncSession, context
    ):
        from src.domains.memories.models import Memory

        user, conversation, _message, entry = context
        memory = Memory(
            user_id=user.id,
            content="Allergique aux crustacés",
            category="health",
            emotional_weight=0,
            trigger_topic="repas",
            usage_nuance="à rappeler avant un restaurant",
            importance=0.8,
            char_count=24,
        )
        async_session.add(memory)
        await async_session.commit()
        await async_session.refresh(memory)

        async_session.add(
            ProvenanceReference(
                user_id=user.id,
                journal_entry_id=entry.id,
                memory_id=memory.id,
                conversation_id=conversation.id,
            )
        )
        with pytest.raises(IntegrityError):
            await async_session.commit()
        await async_session.rollback()


class TestADeletedConversationLeavesATombstone:
    async def test_the_reference_survives_and_carries_no_text(
        self, async_session: AsyncSession, context
    ):
        """The one promise of the design: a deletion is never undone here."""
        user, conversation, message, entry = context
        repo = ProvenanceRepository(async_session)
        await repo.record(
            user_id=user.id,
            journal_entry_id=entry.id,
            conversation_id=conversation.id,
            message_id=message.id,
        )
        await async_session.commit()

        await async_session.delete(conversation)
        await async_session.commit()

        [resolved] = await repo.resolve_for(user_id=user.id, journal_entry_id=entry.id)
        assert resolved.is_tombstone is True
        assert resolved.conversation_id is None
        # The text is GONE, not remembered.
        assert resolved.excerpt is None
        # …and when it happened is still known: that is what a tombstone says.
        assert resolved.captured_at is not None

    async def test_deleting_the_belief_removes_its_references(
        self, async_session: AsyncSession, context
    ):
        """A reference to a deleted belief has no subject left to explain."""
        user, conversation, message, entry = context
        repo = ProvenanceRepository(async_session)
        await repo.record(
            user_id=user.id,
            journal_entry_id=entry.id,
            conversation_id=conversation.id,
            message_id=message.id,
        )
        await async_session.commit()

        await async_session.delete(entry)
        await async_session.commit()

        remaining = (
            await async_session.execute(select(func.count()).select_from(ProvenanceReference))
        ).scalar()
        assert remaining == 0


class TestNothingIsRecordedWithoutSomethingToPointAt:
    async def test_a_reference_with_no_source_is_not_written(
        self, async_session: AsyncSession, context
    ):
        """A richer-looking trail that explains nothing is worse than none."""
        user, _conversation, _message, entry = context
        repo = ProvenanceRepository(async_session)

        assert await repo.record(user_id=user.id, journal_entry_id=entry.id) is None
        await async_session.commit()

        assert await repo.count_for(journal_entry_id=entry.id) == 0

    async def test_a_reference_with_no_subject_is_not_written(
        self, async_session: AsyncSession, context
    ):
        user, conversation, _message, _entry = context
        repo = ProvenanceRepository(async_session)

        assert await repo.record(user_id=user.id, conversation_id=conversation.id) is None
