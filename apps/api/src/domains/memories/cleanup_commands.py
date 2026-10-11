"""Automatic deletion must still match the candidate selected for retention scoring."""

from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memories.models import Memory
from src.domains.memories.protection import PROTECTED_CATEGORIES


async def delete_unchanged_cleanup_candidate(db: AsyncSession, candidate: Memory) -> bool:
    """A concurrent pin, correction, use or supersession withdraws this deletion."""
    deleted: UUID | None = await db.scalar(
        delete(Memory)
        .where(
            Memory.id == candidate.id,
            Memory.user_id == candidate.user_id,
            Memory.pinned.is_(False),
            Memory.invalidated_at.is_(None),
            Memory.category.not_in(PROTECTED_CATEGORIES),
            Memory.updated_at == candidate.updated_at,
            Memory.category == candidate.category,
            Memory.content == candidate.content,
            Memory.importance == candidate.importance,
            Memory.usage_count == candidate.usage_count,
            Memory.last_accessed_at == candidate.last_accessed_at,
        )
        .returning(Memory.id)
        .execution_options(synchronize_session=False)
    )
    return deleted is not None
