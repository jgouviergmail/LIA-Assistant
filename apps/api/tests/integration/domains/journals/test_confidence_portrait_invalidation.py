"""A real confidence downgrade invalidates prose while preserving its proposition."""

from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.domains.journals.consolidation_output import (
    PortraitClaim,
    PortraitSupport,
    grounded_portraits,
)
from src.domains.journals.lifecycle import portrait_is_current
from src.domains.journals.service import JournalService
from src.domains.journals.source_state import portrait_source_state
from src.domains.shared import portrait_sources
from src.domains.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("level", ["L1", "L2", "L3"])
async def test_downgrade_retires_portrait_without_replacing_supported_rule(
    async_engine, monkeypatch, level
):
    monkeypatch.setattr(portrait_sources, "_REGISTRY", {})
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        user = User(
            email=f"confidence-portrait-{uuid4().hex}@example.test",
            hashed_password="x",
            journals_enabled=True,
            is_active=True,
        )
        db.add(user)
        await db.flush()
        service = JournalService(db)
        note = await service.create_entry(
            user.id,
            "user_observations",
            "Compare durable options",
            "For durable commitments, the person asks to compare options before choosing.",
            level=level,
            confidence="high",
            precomputed_embeddings=(None, None),
        )
        if level == "L1":
            for index in range(2):
                await service.update_entry(
                    note,
                    evidence_outcome="evidence",
                    event_key=f"causal:{index}",
                    confidence="high",
                )
        await db.commit()
        await db.refresh(user)
        assert note.confidence == "high"
        claim = PortraitClaim(
            facet="posture",
            text="Pour ses engagements durables, il préfère comparer les possibilités avant de choisir.",
            supports=[PortraitSupport(source=f"journal:{note.id}", quote=note.content)],
        )
        full, brief = grounded_portraits([claim], [note], {})
        user.journal_portrait_full, user.journal_portrait_brief = full, brief
        user.journal_portrait_sources = {
            "journal_revision": user.journal_revision,
            "source_state": await portrait_source_state(db, user),
        }
        await db.commit()
        assert await portrait_is_current(db, user)
        user_id = user.id
    try:
        async with factory() as db:
            service = JournalService(db)
            entry = await service.get_entry_for_user(note.id, user_id)
            original = (entry.content, entry.revision, entry.evidence_count)
            await service.update_entry(entry, confidence="medium", expected_revision=entry.revision)
            await db.commit()
            current_user = await db.get(User, user_id)
            assert entry.confidence == "medium"
            assert (entry.content, entry.revision, entry.evidence_count) == original
            assert not await portrait_is_current(db, current_user)
            assert current_user.journal_portrait_full is current_user.journal_portrait_brief is None
    finally:
        async with factory() as db:
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
