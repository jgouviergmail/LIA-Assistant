"""Retiring a discussion preserves learned records but withdraws its source pointers."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.conversations.models import ConversationMessage
from src.domains.interests.models import UserInterest
from src.domains.journals.models import JournalEntry
from src.domains.memories.models import Memory
from src.domains.shared.provenance import ProvenanceReference
from src.domains.shared.provenance_repository import ProvenanceRepository
from tests.fixtures.learning_sources import Sources
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("erase", [False, True])
async def test_learning_survives_with_only_the_retired_sources_tombstoned(
    async_engine: AsyncEngine, sources: Sources, erase: bool
) -> None:
    owner = sources.main.owner_id
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        memory = Memory(
            user_id=owner, content="An established preference", category="preference", char_count=25
        )
        journal = JournalEntry(
            user_id=owner,
            theme="learnings",
            title="A rule",
            content="A learned rule",
            char_count=14,
        )
        interest = UserInterest(
            user_id=owner,
            topic="Fictional astronomy",
            category="science",
            last_mentioned_at=datetime.now(UTC),
        )
        db.add_all([memory, journal, interest])
        await db.flush()
        for target in (sources.main, sources.annex):
            message = ConversationMessage(
                conversation_id=target.id, role="user", content=f"Evidence {target.kind.value}"
            )
            db.add(message)
            await db.flush()
            for subject in (
                ProvenanceReference(user_id=owner, memory_id=memory.id),
                ProvenanceReference(user_id=owner, journal_entry_id=journal.id),
                ProvenanceReference(user_id=owner, interest_id=interest.id),
            ):
                subject.conversation_id = target.id
                subject.message_id = message.id
                subject.outcome = "origin"
                db.add(subject)
        await db.commit()
        lifecycle = ConversationLifecycle(db)
        retire = lifecycle.request_delete if erase else lifecycle.request_reset
        await retire(owner, sources.annex.id, operation_id=uuid4(), expected_revision=0)
        db.expire_all()
        assert await db.scalar(select(Memory.id).where(Memory.user_id == owner)) is not None
        assert (
            await db.scalar(select(JournalEntry.id).where(JournalEntry.user_id == owner))
            is not None
        )
        assert (
            await db.scalar(select(UserInterest.id).where(UserInterest.user_id == owner))
            is not None
        )
        references = list(
            (
                await db.scalars(
                    select(ProvenanceReference).where(ProvenanceReference.user_id == owner)
                )
            ).all()
        )
        assert len(references) == 6
        assert sum(row.conversation_id == sources.main.id for row in references) == 3
        assert (
            sum(row.conversation_id is None and row.message_id is None for row in references) == 3
        )
        memory_id = await db.scalar(select(Memory.id).where(Memory.user_id == owner))
        assert memory_id is not None
        resolved = await ProvenanceRepository(db).resolve_for(user_id=owner, memory_id=memory_id)
        assert sum(row.is_tombstone for row in resolved) == 1
        assert all(row.excerpt is None for row in resolved if row.is_tombstone)
