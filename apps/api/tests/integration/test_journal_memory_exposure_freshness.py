"""Source freshness follows factual content and actual selected page identity."""

from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.core.config import settings
from src.domains.journals.lifecycle import portrait_is_current
from src.domains.journals.source_state import portrait_source_state
from src.domains.memories.models import Memory
from src.domains.memories.portrait_source import FRESHNESS
from src.domains.memories.repository import MemoryRepository
from src.domains.shared import portrait_sources
from src.domains.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize(
    "mutation", ["same_page_usage", "selection_changes", "nonmax_edit", "delete"]
)
async def test_memory_tracking_preserves_only_unchanged_facts_and_selected_page(
    async_engine, monkeypatch, mutation
):
    monkeypatch.setattr(settings, "journal_consolidation_memories_max", 1)
    monkeypatch.setattr(
        portrait_sources,
        "_REGISTRY",
        {"memories": (None, replace(FRESHNESS, allowed=AsyncMock(return_value=True)))},
    )
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        user = User(
            email=f"memory-freshness-{uuid4().hex}@example.test",
            hashed_password="x",
            journals_enabled=True,
            is_active=True,
        )
        db.add(user)
        await db.flush()
        first = Memory(
            user_id=user.id,
            content="First complete fact.",
            char_count=20,
            category="personal",
            usage_count=2,
        )
        other = Memory(
            user_id=user.id,
            content="Other complete fact.",
            char_count=20,
            category="personal",
            usage_count=0,
        )
        db.add_all([first, other])
        await db.flush()
        state = await portrait_source_state(db, user)
        user.journal_portrait_full = "A supported natural portrait."
        user.journal_portrait_sources = {
            "journal_revision": user.journal_revision,
            "source_state": state,
        }
        await db.commit()
        user_id = user.id
    try:
        async with factory() as db:
            user = await db.get(User, user_id)
            repo = MemoryRepository(db)
            before = [row.id for row in await repo.list_for_portrait(user_id, limit=1)]
            assert before == [first.id]
            if mutation == "same_page_usage":
                await repo.increment_usage([first.id])
            elif mutation == "selection_changes":
                for _ in range(3):
                    await repo.increment_usage([other.id])
            elif mutation == "nonmax_edit":
                current = await db.get(Memory, first.id)
                current.content = "Changed complete fact."
            else:
                await db.execute(delete(Memory).where(Memory.id == other.id))
            await db.commit()
            after = [row.id for row in await repo.list_for_portrait(user_id, limit=1)]
            assert (after == before) is (mutation != "selection_changes")
            assert await portrait_is_current(db, user) is (mutation == "same_page_usage")
    finally:
        async with factory() as db:
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
