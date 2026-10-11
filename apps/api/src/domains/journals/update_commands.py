"""Manual edit preflights source meaning before spend and compares under owner-first locks."""

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError, raise_user_not_found
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.journals.constants import JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH
from src.domains.journals.manual_embeddings import prepare_manual_journal_embeddings
from src.domains.journals.manual_update_projection import (
    ManualJournalUpdate,
    preview_manual_journal_update,
)
from src.domains.journals.models import JournalEntry
from src.domains.journals.removal_snapshot import JournalRemovalSnapshot, journal_removal_snapshot
from src.domains.journals.schemas import JournalEntryResponse, JournalEntryUpdate
from src.domains.journals.service import JournalEmbeddings, JournalService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository


class JournalUpdateCompletionUnknown(RuntimeError):
    """No acknowledgement proves neither failure nor successful edit."""


async def read_manual_journal_update(
    db: AsyncSession,
    actor_id: UUID,
    entry_id: UUID,
    changes: JournalEntryUpdate,
    *,
    locked: bool = False,
    expected: JournalRemovalSnapshot | None = None,
) -> tuple[JournalRemovalSnapshot, ManualJournalUpdate]:
    actor = (
        await UserRepository(db).get_by_id_for_preference_update(actor_id)
        if locked
        else await db.scalar(
            select(User)
            .where(User.id == actor_id, User.is_active, User.deleted_at.is_(None))
            .execution_options(populate_existing=True)
        )
    )
    if actor is None:
        raise_user_not_found(actor_id)
    assert actor is not None
    snapshot = await journal_removal_snapshot(db, actor, entry_id, locked=locked)
    if expected is not None and not expected.matches(snapshot):
        raise ResourceConflictError("journal_entry", detail={"error_code": "STALE_STATE"})
    row = await db.scalar(
        select(JournalEntry)
        .where(JournalEntry.user_id == actor_id, JournalEntry.id == entry_id)
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise ResourceNotFoundError("journal_entry", entry_id)
    projection = await preview_manual_journal_update(db, row, changes)
    if (
        snapshot.entry is None
        or snapshot.entry.model_dump(
            mode="json", exclude={"updated_at", "injection_count", "last_injected_at"}
        )
        != projection.before
    ):
        raise ResourceConflictError("journal_entry", detail={"error_code": "STALE_STATE"})
    return snapshot, projection


async def update_managed_journal_entry(
    db: AsyncSession,
    actor_id: UUID,
    entry_id: UUID,
    data: JournalEntryUpdate,
    *,
    operation_id: UUID | None = None,
    expected: JournalRemovalSnapshot | None = None,
    expected_projection: dict[str, JsonValue] | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: Callable[[], Awaitable[None]] | None = None,
) -> JournalEntryResponse:
    selected = JournalEntryUpdate.model_validate(
        data.model_dump(exclude_unset=True, exclude_none=True)
    )

    async def fence() -> None:
        await require_capability_fresh(db, PlatformCapability.JOURNALS)
        if (
            await db.scalar(
                select(User.id).where(
                    User.id == actor_id, User.is_active, User.deleted_at.is_(None)
                )
            )
            is None
        ):
            raise_user_not_found(actor_id)
        if check is not None:
            await check()

    await fence()
    observed, projected = await read_manual_journal_update(
        db, actor_id, entry_id, selected, expected=expected
    )
    if expected_projection is not None and projected.after != expected_projection:
        raise ResourceConflictError("journal_entry", detail={"error_code": "STALE_STATE"})
    vectors: JournalEmbeddings = (None, None)
    if projected.needs_embeddings:
        assert observed.entry is not None
        values = projected.after
        vectors = await prepare_manual_journal_embeddings(
            actor_id,
            operation_id or uuid4(),
            str(values["title"]),
            str(values["content"]),
            (
                selected.search_hints
                if "search_hints" in selected.model_fields_set
                else observed.entry.search_hints
            ),
            fence,
        )
    current, fresh = await read_manual_journal_update(
        db, actor_id, entry_id, selected, locked=True, expected=observed
    )
    if fresh.after != projected.after:
        raise ResourceConflictError("journal_entry", detail={"error_code": "STALE_STATE"})
    await fence()
    if not fresh.changed:
        assert current.entry is not None
        if receipt is not None:
            receipt.committed = True
            receipt.no_op = True
            receipt.values = {"journal_entry": current.entry.model_dump(mode="json")}
        return current.entry
    return await _settle_manual_update(
        db, actor_id, entry_id, selected, current, fresh, vectors, receipt, fence
    )


async def _settle_manual_update(
    db: AsyncSession,
    actor_id: UUID,
    entry_id: UUID,
    selected: JournalEntryUpdate,
    current: JournalRemovalSnapshot,
    projection: ManualJournalUpdate,
    vectors: JournalEmbeddings,
    receipt: PreferenceWriteReceipt | None,
    fence: Callable[[], Awaitable[None]],
) -> JournalEntryResponse:
    service = JournalService(db)
    row = await service.get_entry_for_user(entry_id, actor_id)
    if row is None or current.entry is None:
        raise ResourceNotFoundError("journal_entry", entry_id)
    updated = await service.update_entry(
        row,
        title=selected.title,
        content=selected.content,
        mood=selected.mood.value if selected.mood else None,
        search_hints=selected.search_hints,
        confidence=selected.confidence.value if selected.confidence else None,
        level=selected.level.value if selected.level else None,
        expected_revision=current.entry.revision,
        max_entry_chars=JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH,
        precomputed_embeddings=vectors,
    )
    await db.flush()
    await db.refresh(updated)
    result = JournalEntryResponse.model_validate(updated)
    public = result.model_dump(
        mode="json", exclude={"updated_at", "injection_count", "last_injected_at"}
    )
    if public != projection.after:
        raise ValueError("Source journal update effects differ from the approved projection")
    await fence()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise JournalUpdateCompletionUnknown from exc
    if receipt is not None:
        receipt.committed = True
        receipt.values = {"journal_entry": result.model_dump(mode="json")}
    return result
