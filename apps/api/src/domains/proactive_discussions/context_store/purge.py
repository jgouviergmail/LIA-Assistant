"""Bounded marker batches preserve atomic forgetting even for a large personal base."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.proactive_discussions.context_store.admission import reference_key
from src.domains.proactive_discussions.context_store.models import (
    ContextItemRecord,
    ContextObservationRecord,
    ContextResumeRecord,
)


async def _write_markers(db: AsyncSession, batch: list[dict[str, UUID | str]]) -> None:
    statement = insert(ContextResumeRecord)
    await db.execute(
        statement.values(batch).on_conflict_do_update(
            index_elements=[ContextResumeRecord.user_id, ContextResumeRecord.root],
            set_={"version": statement.excluded.version},
        )
    )


async def purge_all_data(db: AsyncSession, owner: UUID) -> None:
    """Forget an account's whole context, keeping markers of what was forgotten.

    Every observation leaves a marker of its root and reference at its version,
    written in bounded batches, so an unchanged fact is not rebuilt from an old
    read; then every item and observation is deleted.

    Args:
        db: The session to write with.
        owner: The account.
    """
    size = settings.discussion_context_purge_batch_size
    rows = await db.stream_scalars(
        select(ContextObservationRecord)
        .where(
            ContextObservationRecord.user_id == owner,
        )
        .execution_options(yield_per=size)
    )
    batch: list[dict[str, UUID | str]] = []
    try:
        async for row in rows:
            roots = [row.root]
            reference = row.data.get("reference")
            if isinstance(reference, str):
                roots.append(reference_key(reference))
            batch.extend({"user_id": owner, "root": root, "version": row.version} for root in roots)
            if len(batch) >= 2 * size:
                await _write_markers(db, batch)
                batch = []
        if batch:
            await _write_markers(db, batch)
    finally:
        await rows.close()
    await db.execute(delete(ContextItemRecord).where(ContextItemRecord.user_id == owner))
    await db.execute(
        delete(ContextObservationRecord).where(ContextObservationRecord.user_id == owner)
    )
