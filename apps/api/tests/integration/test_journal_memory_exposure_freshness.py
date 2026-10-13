"""Source freshness follows the factual content of the WHOLE record, never its bookkeeping."""

from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.domains.journals.lifecycle import portrait_is_current
from src.domains.journals.source_state import portrait_source_state
from src.domains.memories.models import Memory
from src.domains.memories.portrait_source import FRESHNESS
from src.domains.memories.repository import MemoryRepository
from src.domains.shared import portrait_sources
from src.domains.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("mutation", ["usage_only", "edit", "delete", "add"])
async def test_memory_tracking_follows_the_facts_of_every_row(async_engine, monkeypatch, mutation):
    """Every memory is read (ADR-343): an edit, a deletion or an addition anywhere in the
    record moves the portrait; a usage counter — bookkeeping — never does."""
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
            if mutation == "usage_only":
                await repo.increment_usage([first.id, other.id])
            elif mutation == "edit":
                current = await db.get(Memory, other.id)
                current.content = "Changed complete fact."
            elif mutation == "delete":
                await db.execute(delete(Memory).where(Memory.id == other.id))
            else:
                db.add(
                    Memory(
                        user_id=user_id,
                        content="A third complete fact.",
                        char_count=21,
                        category="personal",
                        usage_count=0,
                    )
                )
            await db.commit()
            assert await portrait_is_current(db, user) is (mutation == "usage_only")
    finally:
        async with factory() as db:
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
