"""Manual creation honors the public API limit and binds provider work to its owner."""

from collections.abc import Awaitable, Callable
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, raise_user_not_found
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.journals.constants import JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH
from src.domains.journals.evidence import effective_confidence
from src.domains.journals.manual_embeddings import prepare_manual_journal_embeddings
from src.domains.journals.models import JournalEntry, JournalEntrySource
from src.domains.journals.schemas import JournalEntryCreate, JournalEntryResponse
from src.domains.journals.service import JournalService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository


class JournalCreationCompletionUnknown(RuntimeError):
    """Paid work may finish even if the entry's commit acknowledgement is missing."""


class JournalCreationKind(StrEnum):
    MANUAL = "manual"
    PORTRAIT_CORRECTION = "portrait_correction"


_CLASSIFICATION = {
    JournalCreationKind.MANUAL: (JournalEntrySource.MANUAL, "L1", "medium"),
    JournalCreationKind.PORTRAIT_CORRECTION: (JournalEntrySource.USER_CORRECTION, "L0", "high"),
}


def _verify_created_entry(
    selected: JournalEntryCreate,
    observed: JournalEntryResponse,
    identity: UUID,
    kind: JournalCreationKind,
) -> None:
    source, level, confidence = _CLASSIFICATION[kind]
    expected = selected.model_dump(mode="json")
    actual = observed.model_dump(mode="json")
    if (
        observed.id != identity
        or observed.source != source
        or observed.level.value != level
        or observed.confidence.value != effective_confidence(confidence, level, 0)
        or observed.char_count != len(selected.content)
    ):
        raise ValueError("Source manual creation effects were not observed")
    if {name: actual[name] for name in expected} != expected:
        raise ValueError("Source manual creation changed approved configuration")


async def create_managed_journal_entry(
    db: AsyncSession,
    actor_id: UUID,
    data: JournalEntryCreate,
    *,
    entry_id: UUID | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: Callable[[], Awaitable[None]] | None = None,
    check_scope: Callable[[], Awaitable[None]] | None = None,
    kind: JournalCreationKind = JournalCreationKind.MANUAL,
    observe: Callable[[JournalEntryResponse], Awaitable[None]] | None = None,
) -> JournalEntryResponse:
    selected = JournalEntryCreate.model_validate(data.model_dump())
    identity = entry_id or uuid4()
    source, level, confidence = _CLASSIFICATION[kind]

    async def fence() -> None:
        await require_capability_fresh(db, PlatformCapability.JOURNALS)
        exists = await db.scalar(
            select(User.id).where(User.id == actor_id, User.is_active, User.deleted_at.is_(None))
        )
        if exists is None:
            raise_user_not_found(actor_id)
        if check is not None:
            await check()

    await fence()
    if check_scope is not None:
        await check_scope()
    if await db.scalar(select(JournalEntry.id).where(JournalEntry.id == identity)) is not None:
        raise ResourceConflictError("journal_entry", detail={"error_code": "STALE_STATE"})
    prepared = await prepare_manual_journal_embeddings(
        actor_id, identity, selected.title, selected.content, selected.search_hints, fence
    )
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None:
        raise_user_not_found(actor_id)
    await fence()
    if check_scope is not None:
        await check_scope()
    created = await JournalService(db).create_entry(
        user_id=actor_id,
        theme=selected.theme.value,
        title=selected.title,
        content=selected.content,
        mood=selected.mood.value,
        source=source.value,
        level=level,
        confidence=confidence,
        search_hints=selected.search_hints,
        max_entry_chars=JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH,
        precomputed_embeddings=prepared,
        entry_id=identity,
    )
    await db.flush()
    await db.refresh(created)
    observed = JournalEntryResponse.model_validate(created)
    _verify_created_entry(selected, observed, identity, kind)
    if observe is not None:
        await observe(observed)
    await fence()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise JournalCreationCompletionUnknown from exc
    if receipt is not None:
        receipt.committed = True
        receipt.values = {"journal_entry": observed.model_dump(mode="json")}
    return observed
