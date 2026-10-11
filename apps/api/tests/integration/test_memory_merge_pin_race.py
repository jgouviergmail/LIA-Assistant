"""Consolidation must retain a pair member protected or corrected after candidate selection."""

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memories.models import Memory
from src.domains.memories.repository import MemoryRepository
from src.domains.users.models import User
from src.infrastructure.scheduler.memory_consolidation import _apply_merge

pytestmark = pytest.mark.integration


async def test_rejected_pair_does_not_refresh_later_candidates(
    async_session: AsyncSession, test_user: User
) -> None:
    facts = [
        Memory(
            user_id=test_user.id,
            content=text,
            category="personal",
            importance=0.7,
            pinned=False,
            char_count=len(text),
        )
        for text in ("First survivor", "Selected loser", "Second survivor")
    ]
    async_session.add_all(facts)
    await async_session.commit()
    first, loser, second = facts
    await async_session.execute(
        update(Memory)
        .where(Memory.id == loser.id)
        .values(content="Corrected after selection")
        .execution_options(synchronize_session=False)
    )
    await async_session.commit()
    repo = MemoryRepository(async_session)
    assert await _apply_merge(repo, first, loser) is False
    assert await _apply_merge(repo, second, loser) is False


@pytest.mark.parametrize(
    "intervention",
    ["none", "loser_pin", "survivor_pin", "corrected", "used", "procedural"],
)
async def test_merge_keeps_both_memories_when_the_selected_pair_changes(
    async_session: AsyncSession,
    test_user: User,
    intervention: str,
) -> None:
    survivor = Memory(
        user_id=test_user.id,
        content="Surviving fact",
        category="personal",
        importance=0.8,
        pinned=False,
        char_count=14,
    )
    loser = Memory(
        user_id=test_user.id,
        content="Superseded fact",
        category="personal",
        importance=0.7,
        pinned=False,
        char_count=15,
    )
    async_session.add_all([survivor, loser])
    await async_session.commit()
    identity = loser.id
    if intervention != "none":
        selected = survivor.id if intervention == "survivor_pin" else identity
        changes: dict[str, object] = (
            {"pinned": True}
            if intervention.endswith("pin")
            else (
                {"content": "Corrected fact"}
                if intervention == "corrected"
                else (
                    {"category": "procedural"}
                    if intervention == "procedural"
                    else {"usage_count": 1}
                )
            )
        )
        await async_session.execute(
            update(Memory)
            .where(Memory.id == selected)
            .values(changes)
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    assert await _apply_merge(MemoryRepository(async_session), survivor, loser) is (
        intervention == "none"
    )
    await async_session.commit()
    current = await async_session.scalar(
        select(Memory).where(Memory.id == identity).execution_options(populate_existing=True)
    )
    assert current is not None
    if intervention == "none":
        assert current.invalidated_at is not None and current.superseded_by_id == survivor.id
    else:
        assert current.invalidated_at is None and current.superseded_by_id is None
