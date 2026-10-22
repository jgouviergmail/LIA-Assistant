"""Expiration is lifecycle maintenance, independent of consent to produce new messages."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.proactive_discussions.context_store.models import (
    ContextItemRecord,
    ContextObservationRecord,
)
from src.domains.proactive_discussions.context_store.repository import ContextRepository


async def expire_context(db: AsyncSession, owner: UUID, *, now: datetime) -> int:
    """Delete the context items and observations past their retention.

    Retention is lifecycle, never forgetting: when anything expired, the generation
    moves and the ready context is cleared — nothing is reused from what aged out —
    and nothing else. The context epoch, the run in progress and the pending opening
    are left alone: every other checkpoint still holds, and what a run publishes
    later rests on facts it reads then, admitted again with their own retention.
    Measured 2026-10-21: the location and weather observations live 15 and 30
    minutes, so invalidating the context at each expiry voided every checkpoint
    several times an hour (each opening run re-interpreted twelve facts), abandoned
    the run in flight and expired every opening 4 to 16 minutes after LIA wrote it.
    The person's forgetting acts — a purge, an exclusion, an erased source — still
    move the epoch.

    Args:
        db: The session to write with.
        owner: The account.
        now: The current instant.

    Returns:
        The number of context items deleted.
    """
    repo = ContextRepository(db)
    await repo._owner(owner)
    state = await repo._state(owner, lock=True)
    items = tuple(
        (
            await db.scalars(
                delete(ContextItemRecord)
                .where(ContextItemRecord.user_id == owner, ContextItemRecord.expires_at <= now)
                .returning(ContextItemRecord.id)
            )
        ).all()
    )
    observations = tuple(
        (
            await db.scalars(
                delete(ContextObservationRecord)
                .where(
                    ContextObservationRecord.user_id == owner,
                    ContextObservationRecord.expires_at <= now,
                )
                .returning(ContextObservationRecord.id)
            )
        ).all()
    )
    if items or observations:
        state.generation += 1
        state.ready_context = None
    return len(items)
