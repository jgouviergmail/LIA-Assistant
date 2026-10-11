"""Invalidate derived portraits and settle journal work by the revision read.

Every writer takes the owner lock before entry locks. No method commits: the
caller owns the transaction and its consent fence.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import case, cast, func, select, update
from sqlalchemy.dialects.postgresql import JSONB, array
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User


async def lock_journal_owner(db: AsyncSession, user_id: UUID) -> None:
    """Serialize short journal settlements in a single lock order."""
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())


async def mark_journal_changed(
    db: AsyncSession, user_id: UUID, *, invalidate_portrait: bool = True
) -> None:
    """Include creates, edits, evidence and deletions in the work revision."""
    values: dict[str, Any] = {"journal_revision": User.journal_revision + 1}
    if invalidate_portrait:
        values.update(
            journal_portrait_full=None,
            journal_portrait_brief=None,
            journal_portrait_compiled_at=None,
            journal_portrait_sources=None,
        )
    else:
        # A confirming reaction changes work/evidence, not the selected words.
        # Advance only an already-versioned portrait; never bless legacy prose.
        values["journal_portrait_sources"] = case(
            (
                User.journal_portrait_sources["journal_revision"]
                == func.to_jsonb(User.journal_revision),
                func.jsonb_set(
                    User.journal_portrait_sources,
                    array(["journal_revision"]),
                    func.to_jsonb(User.journal_revision + 1),
                ),
            ),
            else_=cast(User.journal_portrait_sources, JSONB),
        )
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(**values)
        .execution_options(synchronize_session=False)
    )


async def portrait_is_current(db: AsyncSession, user: User) -> bool:
    """Reject an unversioned portrait or one whose authorized sources moved."""
    from src.domains.journals.source_state import portrait_source_state

    provenance: Any = user.journal_portrait_sources
    if not isinstance(provenance, dict):
        return False
    revision = provenance.get("journal_revision")
    if (
        not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision != user.journal_revision
    ):
        return False
    expected = provenance.get("source_state")
    if not isinstance(expected, dict):
        return False
    return expected == await portrait_source_state(db, user)
