"""Apply individually isolated actions after the caller's consent/owner guard."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.journals.extraction_actions import validate_extraction_actions
from src.domains.journals.models import JournalEntry
from src.domains.journals.schemas import ExtractedJournalEntry
from src.domains.journals.service import JournalEmbeddings, JournalService
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)
OriginRecorder = Callable[..., Awaitable[Any]]
EmbeddingInput = tuple[str, str, list[str] | None]


@dataclass(frozen=True)
class ExtractionSettlement:
    """The admission-time identities needed to validate an action at settlement."""

    user_id: str
    session_id: str
    personality_code: str | None
    max_entry_chars: int
    event_key: str
    known_ids: set[str]
    previous_verified_ids: set[str]
    loaded_revisions: dict[str, int]
    previous_revisions: dict[str, int]
    prepared_inputs: dict[str, EmbeddingInput | None] = field(default_factory=dict)


def desired_embedding_input(
    action: ExtractedJournalEntry, entry: JournalEntry
) -> EmbeddingInput | None:
    """The exact resulting fields whose vector may be prepared outside the lock."""
    if entry.level in ("L2", "L3"):
        return None
    changed = any(
        value is not None and value != getattr(entry, key)
        for key, value in (
            ("title", action.title),
            ("content", action.content),
            ("search_hints", action.search_hints),
        )
    )
    if not changed:
        return None
    hints = action.search_hints if action.search_hints is not None else entry.search_hints
    return (
        action.title if action.title is not None else entry.title,
        action.content if action.content is not None else entry.content,
        list(hints) if hints is not None else None,
    )


async def _create(
    db: AsyncSession,
    service: JournalService,
    action: ExtractedJournalEntry,
    context: ExtractionSettlement,
    record_origin: OriginRecorder,
    embeddings: JournalEmbeddings,
) -> int:
    if not (action.theme and action.title and action.content):
        return 0
    created = await service.create_entry(
        user_id=UUID(context.user_id),
        theme=action.theme.value,
        title=action.title,
        content=action.content,
        mood=action.mood.value if action.mood else "reflective",
        source="conversation",
        session_id=context.session_id,
        personality_code=context.personality_code,
        max_entry_chars=context.max_entry_chars,
        search_hints=action.search_hints,
        confidence=action.confidence.value if action.confidence else "medium",
        level=action.level.value if action.level else "L1",
        precomputed_embeddings=embeddings,
    )
    await record_origin(
        db,
        user_id=UUID(context.user_id),
        source=context.session_id,
        journal_entry_id=created.id,
    )
    return 1


async def _owned_entry(
    service: JournalService, action: ExtractedJournalEntry, context: ExtractionSettlement
) -> JournalEntry | None:
    if not action.entry_id:
        return None
    entry = await service.repo.get_by_id(UUID(action.entry_id))
    return entry if entry and str(entry.user_id) == context.user_id else None


def _expected_revision(action: ExtractedJournalEntry, context: ExtractionSettlement) -> int | None:
    assert action.entry_id is not None
    if action.evidence_outcome:
        return context.previous_revisions.get(action.entry_id)
    return context.loaded_revisions.get(action.entry_id) or context.previous_revisions.get(
        action.entry_id
    )


async def _update(
    service: JournalService,
    action: ExtractedJournalEntry,
    context: ExtractionSettlement,
    embeddings: JournalEmbeddings,
) -> int:
    entry = await _owned_entry(service, action, context)
    if entry is None:
        return 0
    # Consolidation may have promoted the row during the model call. The
    # caller holds the owner lock while this current-level guard runs.
    fresh = validate_extraction_actions(
        [action],
        known_ids=context.known_ids,
        previous_verified_ids=context.previous_verified_ids,
        entry_levels={str(entry.id): entry.level},
        max_entry_chars=context.max_entry_chars,
    )
    if not fresh:
        return 0
    action = fresh[0]
    if desired_embedding_input(action, entry) != context.prepared_inputs.get(str(entry.id)):
        logger.info("journal_extraction_prepared_payload_changed", entry_id=str(entry.id))
        return 0
    await service.update_entry(
        entry=entry,
        title=action.title,
        content=action.content,
        mood=action.mood.value if action.mood else None,
        max_entry_chars=context.max_entry_chars,
        search_hints=action.search_hints,
        confidence=action.confidence.value if action.confidence else None,
        evidence_outcome=action.evidence_outcome,
        event_key=context.event_key,
        evidence_source=context.session_id,
        expected_revision=_expected_revision(action, context),
        level=action.level.value if action.level else None,
        theme=action.theme.value if action.theme else None,
        precomputed_embeddings=embeddings,
    )
    return 1


async def _delete(
    service: JournalService, action: ExtractedJournalEntry, context: ExtractionSettlement
) -> int:
    entry = await _owned_entry(service, action, context)
    if entry is None or entry.level not in ("L0", "L1"):
        return 0
    await service.delete_entry(entry, expected_revision=_expected_revision(action, context))
    return 1


async def _apply(
    db: AsyncSession,
    service: JournalService,
    action: ExtractedJournalEntry,
    context: ExtractionSettlement,
    record_origin: OriginRecorder,
    embeddings: JournalEmbeddings,
) -> int:
    if action.action == "create":
        return await _create(db, service, action, context, record_origin, embeddings)
    if action.action == "update":
        return await _update(service, action, context, embeddings)
    return await _delete(service, action, context)


async def apply_extraction_actions(
    db: AsyncSession,
    service: JournalService,
    actions: list[ExtractedJournalEntry],
    context: ExtractionSettlement,
    record_origin: OriginRecorder,
    prepared: list[JournalEmbeddings | None],
) -> int:
    """One SAVEPOINT per independent action; the caller commits the outer transaction."""
    applied = 0
    for action, embeddings in zip(actions, prepared, strict=True):
        if embeddings is None:
            continue
        try:
            async with db.begin_nested():
                applied += await _apply(db, service, action, context, record_origin, embeddings)
        except Exception as exc:
            logger.warning(
                "journal_extraction_action_failed",
                user_id=context.user_id,
                action=action.action,
                error=str(exc),
            )
            continue
    return applied
