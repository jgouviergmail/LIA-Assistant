"""Atomic source-lifecycle fencing without importing another domain's ORM models.

A composition module, outside every domain and outside the proactive package:
the domains that end a source (an SMS erasure, a connector removal, a
conversation reset) import it at module level. Inside ``domains/shared`` it
closed a conversations <-> shared cycle; inside ``infrastructure/proactive``
the package's heavy ``__init__`` forced every caller into a hidden local import.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import String, case, delete, func, select, update
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.shared.discussion_sources import SourceKey
from src.infrastructure.database.models import Base


async def invalidate_discussion_sources(
    db: AsyncSession, owner: UUID, sources: tuple[SourceKey, ...]
) -> None:
    """Forget everything derived from sources that ended, and fence every run.

    The items resting on those sources' observations and the observations
    themselves are deleted; the context epoch and the run fence move, the run in
    progress is abandoned, the pending opening expires and its undelivered outbox
    row is cancelled (uncertain when mid-send). Nothing happens for an inactive
    account or one that never set discussions up.

    Args:
        db: The caller's session, committed by the caller.
        owner: The account.
        sources: The sources that ended.
    """
    tables = Base.metadata.tables
    if not sources or "discussion_preferences" not in tables:
        return
    users = tables["users"]
    active = await db.scalar(
        select(users.c.id)
        .where(users.c.id == owner, users.c.is_active.is_(True), users.c.deleted_at.is_(None))
        .with_for_update(read=True)
    )
    if active is None:
        return
    pref = tables["discussion_preferences"]
    identity = await db.scalar(select(pref.c.id).where(pref.c.user_id == owner).with_for_update())
    if identity is None:
        return
    now = datetime.now(UTC)
    observations = tables["discussion_context_observations"]
    items = tables["discussion_context_items"]
    roots = (
        select(func.coalesce(func.array_agg(observations.c.root), array([], type_=String(64))))
        .where(
            observations.c.user_id == owner,
            observations.c.source.in_([source.value for source in sources]),
        )
        .scalar_subquery()
    )
    await db.execute(
        delete(items).where(items.c.user_id == owner, items.c.root_keys.overlap(roots))
    )
    await db.execute(
        delete(observations).where(
            observations.c.user_id == owner,
            observations.c.source.in_([source.value for source in sources]),
        )
    )
    await db.execute(
        update(pref)
        .where(pref.c.user_id == owner)
        .values(
            context_epoch=pref.c.context_epoch + 1,
            run_fence=pref.c.run_fence + 1,
            active_run_id=None,
            lease_until=None,
        )
    )
    runs = tables["discussion_runs"]
    await db.execute(
        update(runs)
        .where(runs.c.user_id == owner, runs.c.state == "claimed")
        .values(state="abandoned", settled_at=now)
    )
    openings = tables["discussion_openings"]
    await db.execute(
        update(openings)
        .where(openings.c.user_id == owner, openings.c.state == "pending")
        .values(state="expired", expires_at=now)
    )
    outbox = tables["discussion_outbox"]
    await db.execute(
        update(outbox)
        .where(outbox.c.user_id == owner, outbox.c.state.in_(("pending", "dispatching")))
        .values(
            state=case((outbox.c.state == "dispatching", "uncertain"), else_="cancelled"),
        )
    )
    states = tables["discussion_context_states"]
    await db.execute(
        update(states)
        .where(states.c.user_id == owner)
        .values(generation=states.c.generation + 1, coverage=[])
    )
    await db.flush()


async def invalidate_conversation_discussions(db: AsyncSession, owner: UUID) -> None:
    """Forget what was derived from the conversation, after a conversation reset.

    Args:
        db: The caller's session, committed by the caller.
        owner: The account.
    """
    await invalidate_discussion_sources(db, owner, (SourceKey.CONVERSATIONS,))
