"""Apply automatic consolidation only while both selected facts remain unchanged."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memories.models import Memory
from src.domains.memories.protection import PROTECTED_CATEGORIES


class _Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    pinned: bool
    invalidated_at: datetime | None
    user_id: UUID
    content: str
    category: str
    importance: float
    emotional_weight: int
    usage_count: int
    last_accessed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def capture(cls, memory: Memory) -> _Candidate:
        return cls(
            id=memory.id,
            pinned=memory.pinned,
            invalidated_at=memory.invalidated_at,
            user_id=memory.user_id,
            content=memory.content,
            category=memory.category,
            importance=memory.importance,
            emotional_weight=memory.emotional_weight,
            usage_count=memory.usage_count,
            last_accessed_at=memory.last_accessed_at,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )


def _still_eligible(row: _Candidate, expected: _Candidate) -> bool:
    return (
        not row.pinned
        and row.invalidated_at is None
        and row.category not in PROTECTED_CATEGORIES
        and row == expected
    )


async def merge_unchanged_candidates(db: AsyncSession, survivor: Memory, loser: Memory) -> bool:
    """Lock in stable order without mutating the job's selected candidate objects."""
    if survivor.id == loser.id or survivor.user_id != loser.user_id:
        return False
    expected = {survivor.id: _Candidate.capture(survivor), loser.id: _Candidate.capture(loser)}
    result = await db.execute(
        select(
            Memory.id,
            Memory.pinned,
            Memory.invalidated_at,
            Memory.user_id,
            Memory.content,
            Memory.category,
            Memory.importance,
            Memory.emotional_weight,
            Memory.usage_count,
            Memory.last_accessed_at,
            Memory.created_at,
            Memory.updated_at,
        )
        .where(Memory.id.in_(expected), Memory.user_id == survivor.user_id)
        .order_by(Memory.id)
        .with_for_update()
        .execution_options(autoflush=False)
    )
    rows = [_Candidate.model_validate(row) for row in result.mappings()]
    if len(rows) != 2 or any(not _still_eligible(row, expected[row.id]) for row in rows):
        return False
    await db.execute(
        update(Memory)
        .where(Memory.id == loser.id, Memory.user_id == loser.user_id)
        .values(invalidated_at=datetime.now(UTC), superseded_by_id=survivor.id)
        .execution_options(synchronize_session=False, autoflush=False)
    )
    return True
