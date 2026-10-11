"""Manual management serializes with automatic writers and maintenance."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from src.core.exceptions import AuthorizationError, raise_memory_not_found
from src.domains.memories.models import Memory
from src.domains.users.models import User


async def lock_active_owned_memory(db: AsyncSession, actor_id: UUID, memory_id: UUID) -> Memory:
    """Keep the user's consent lock before the row lock, until caller commit."""
    await lock_memory_actor(db, actor_id)
    return await get_active_owned_memory(db, actor_id, memory_id, for_update=True)


async def lock_memory_actor(db: AsyncSession, actor_id: UUID) -> User:
    """Serialize explicit management with automatic extraction on the source user row."""
    actor: User | None = await db.scalar(
        select(User)
        .where(User.id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if actor is None or not actor.is_active or actor.is_deleted:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    return actor


async def get_active_owned_memory(
    db: AsyncSession, actor_id: UUID, memory_id: UUID, *, for_update: bool = False
) -> Memory:
    """Refresh public management fields; callers separately authorize the current actor."""
    query = (
        select(Memory)
        .where(Memory.id == memory_id, Memory.user_id == actor_id, Memory.invalidated_at.is_(None))
        .options(
            defer(Memory.embedding),
            defer(Memory.keyword_embedding),
            defer(Memory.context_biometric),
        )
        .execution_options(populate_existing=True)
    )
    if for_update:
        query = query.with_for_update()
    row: Memory | None = await db.scalar(query)
    if row is None:
        raise_memory_not_found(str(memory_id))
    return row


async def set_locked_memory_pin(db: AsyncSession, row: Memory, pinned: bool) -> None:
    """The caller holds lock_active_owned_memory and owns the transaction."""
    row.pinned = pinned
    await db.flush()
