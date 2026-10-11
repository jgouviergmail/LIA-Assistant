"""UI and native removals share owner-first locking and source invalidation."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError, raise_user_not_found
from src.domains.journals.models import JournalEntry
from src.domains.journals.removal_snapshot import JournalRemovalSnapshot, journal_removal_snapshot
from src.domains.journals.service import JournalService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository


class JournalRemovalCompletionUnknown(RuntimeError):
    """A missing commit acknowledgement cannot prove erasure."""


async def _verify_removed_scope(
    db: AsyncSession, actor_id: UUID, entry_id: UUID | None, previous_revision: int
) -> None:
    remaining = (
        select(func.count()).select_from(JournalEntry).where(JournalEntry.user_id == actor_id)
    )
    if entry_id is not None:
        remaining = remaining.where(JournalEntry.id == entry_id)
    portrait = (
        await db.execute(
            select(
                User.journal_revision,
                User.journal_portrait_full,
                User.journal_portrait_brief,
                User.journal_portrait_compiled_at,
                User.journal_portrait_sources,
            ).where(User.id == actor_id)
        )
    ).one()
    if (
        await db.scalar(remaining) != 0
        or portrait[0] != previous_revision + 1
        or any(value is not None for value in portrait[1:])
    ):
        raise ValueError("Source journal removal effects were not observed")


async def remove_journal_entries(
    db: AsyncSession,
    actor_id: UUID,
    entry_id: UUID | None,
    *,
    expected: JournalRemovalSnapshot | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: Callable[[], Awaitable[None]] | None = None,
) -> None:
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None:
        raise_user_not_found(actor_id)
    assert actor is not None
    if check is not None:
        await check()
    observed = await journal_removal_snapshot(db, actor, entry_id, locked=True)
    previous_revision = actor.journal_revision
    if expected is not None and not expected.matches(observed):
        raise ResourceConflictError("journal_entries", detail={"error_code": "STALE_STATE"})
    service = JournalService(db)
    if entry_id is None:
        await service.delete_all_for_user(actor_id)
    else:
        entry = await service.get_entry_for_user(entry_id, actor_id)
        if entry is None:
            raise ResourceNotFoundError("journal_entry", entry_id)
        await db.refresh(entry)
        await service.delete_entry(entry, expected_revision=entry.revision)
    await db.flush()
    await _verify_removed_scope(db, actor_id, entry_id, previous_revision)
    if check is not None:
        await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise JournalRemovalCompletionUnknown from exc
    if receipt is not None:
        receipt.committed = True
        receipt.values = {"journal_entries_to_delete": None}
