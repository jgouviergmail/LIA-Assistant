"""A journal source is the business discussion, never its rotating runtime identifier."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.journals.constants import JOURNAL_ENTRY_CONTENT_MAX_LENGTH
from src.domains.journals.extraction_settlement import ExtractionSettlement, _create
from src.domains.journals.schemas import ExtractedJournalEntry
from src.domains.journals.service import JournalService
from src.domains.shared.provenance import ProvenanceReference
from src.domains.shared.provenance_capture import record_origin
from tests.fixtures.learning_sources import Sources
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration


async def test_created_journal_entry_retains_business_provenance_with_distinct_runtime(
    async_engine: AsyncEngine, sources: Sources
) -> None:
    target = sources.annex
    context = ExtractionSettlement(
        user_id=str(target.owner_id),
        session_id=str(target.runtime_id),
        conversation_id=str(target.id),
        personality_code=None,
        max_entry_chars=JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
        event_key=str(uuid4()),
        known_ids=set(),
        previous_verified_ids=set(),
        loaded_revisions={},
        previous_revisions={},
    )
    action = ExtractedJournalEntry(
        action="create",
        theme="learnings",
        title="A fictional rule",
        content="WHEN explaining a change -> DO show the evidence BECAUSE the user needs to verify it.",
    )
    async with AsyncSession(async_engine) as db:
        assert (
            await _create(db, JournalService(db), action, context, record_origin, (None, None)) == 1
        )
        await db.commit()
        reference = await db.scalar(
            select(ProvenanceReference).where(ProvenanceReference.user_id == target.owner_id)
        )
        assert reference is not None
        assert reference.conversation_id == target.id
        assert reference.conversation_id != UUID(context.session_id)
