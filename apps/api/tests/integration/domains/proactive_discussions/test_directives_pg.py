"""Every active procedural rule is binding, independently of factual source choices."""

from uuid import UUID

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.memories.models import Memory
from src.domains.proactive_discussions.directives import (
    DirectiveBudgetExceeded,
    load_directive_snapshot,
)
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_rule_201_is_kept_and_usage_bookkeeping_does_not_change_the_revision(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "memory_extraction_enabled", True)
    async with AsyncSession(async_engine) as db:
        db.add_all(
            [
                Memory(
                    user_id=discussion_owner,
                    content=f"Rule {index}: ask before a personal follow-up.",
                    category="procedural",
                    pinned=True,
                    char_count=50,
                    usage_count=0,
                )
                for index in range(205)
            ]
        )
        db.add(
            Memory(
                user_id=discussion_owner,
                content="Not a directive",
                category="personal",
                char_count=15,
            )
        )
        await db.commit()
        first = await load_directive_snapshot(
            db, discussion_owner, count_tokens=len, max_tokens=50000
        )
        assert first.enabled and len(first.rules) == 205
        assert any(rule.text.startswith("Rule 204:") for rule in first.rules)
        # The native MEMORY operator switch governs learning, not existing instructions.
        monkeypatch.setattr(settings, "memory_extraction_enabled", False)
        still_binding = await load_directive_snapshot(
            db, discussion_owner, count_tokens=len, max_tokens=50000
        )
        assert still_binding.revision == first.revision and len(still_binding.rules) == 205
        await db.execute(
            update(Memory).where(Memory.user_id == discussion_owner).values(usage_count=23)
        )
        await db.commit()
        assert (
            await load_directive_snapshot(db, discussion_owner, count_tokens=len, max_tokens=50000)
        ).revision == first.revision
        with pytest.raises(DirectiveBudgetExceeded):
            await load_directive_snapshot(db, discussion_owner, count_tokens=len, max_tokens=100)
        await db.execute(
            update(Memory)
            .where(Memory.user_id == discussion_owner, Memory.category == "procedural")
            .values(content="Do not mention that topic.")
        )
        await db.commit()
        assert (
            await load_directive_snapshot(db, discussion_owner, count_tokens=len, max_tokens=50000)
        ).revision != first.revision


async def test_global_memory_consent_closes_rule_reads_without_affecting_structured_preferences(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "memory_extraction_enabled", True)
    async with AsyncSession(async_engine) as db:
        await db.execute(
            update(User).where(User.id == discussion_owner).values(memory_enabled=False)
        )
        await db.commit()
        snapshot = await load_directive_snapshot(
            db, discussion_owner, count_tokens=len, max_tokens=1000
        )
        assert not snapshot.enabled and snapshot.rules == ()
