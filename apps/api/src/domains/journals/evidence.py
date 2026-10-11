"""Revision-bound journal updates and idempotent reaction accounting.

All writes lock the owner before the entry. Embedding work is prepared by
the service before this short critical section; no model is called here.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from src.core.exceptions import ResourceConflictError
from src.domains.journals.evidence_models import JournalEvidenceEvent
from src.domains.journals.lifecycle import lock_journal_owner, mark_journal_changed
from src.domains.journals.models import JournalEntry
from src.domains.shared.provenance_capture import conversation_id_of, record_outcome
from src.infrastructure.database.models import Base
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_journals import (
    journal_confidence_clamped_total,
    journal_consolidation_promotions_total,
    journal_evidence_total,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
RESPONSE_EVENT_PREFIX = "response:"


def clamp_confidence(
    confidence: str,
    level: str,
    evidence_count: int,
    source: str,
    contradiction_count: int = 0,
) -> str:
    """The evidence count must be independently stored current-rule events."""
    effective = effective_confidence(confidence, level, evidence_count, contradiction_count)
    if effective == "medium" and confidence == "high":
        with suppress(Exception):
            journal_confidence_clamped_total.labels(source=source).inc()
        logger.info("journal_confidence_clamped", level=level, source=source)
    return effective


def effective_confidence(
    confidence: str, level: str, evidence_count: int, contradiction_count: int = 0
) -> str:
    """Pure source policy shared by observation/approval and recorded writes."""
    if contradiction_count > 0:
        return "low"
    if confidence == "high" and level in ("L0", "L1") and evidence_count < 2:
        return "medium"
    return confidence


def stale_rule() -> ResourceConflictError:
    """Return the existing API conflict vocabulary for a stale proposal."""
    return ResourceConflictError("journal_entry", detail={"error_code": "STALE_JOURNAL_RULE"})


async def owned_conversation(db: AsyncSession, user_id: UUID, source: str | None) -> UUID | None:
    """An unknown/deleted/foreign source leaves an honest empty pointer."""
    conversation_id = conversation_id_of(source)
    if conversation_id is None:
        return None
    conversations = Base.metadata.tables["conversations"]
    result = await db.execute(
        select(conversations.c.id).where(
            conversations.c.id == conversation_id,
            conversations.c.user_id == user_id,
            conversations.c.deleted_at.is_(None),
        )
    )
    return cast(UUID | None, result.scalar_one_or_none())


async def record_evidence_event(
    db: AsyncSession,
    entry: JournalEntry,
    outcome: str,
    event_key: str | None,
    source: str | None,
) -> tuple[bool, UUID | None]:
    """Claim one reaction once for this revision, before incrementing."""
    if not event_key or len(event_key) > 200:
        raise ValueError("Journal evidence requires a nonempty event key of at most 200 characters")
    conversation_id = await owned_conversation(db, entry.user_id, source)
    result = await db.execute(
        insert(JournalEvidenceEvent)
        .values(
            id=uuid4(),
            user_id=entry.user_id,
            journal_entry_id=entry.id,
            rule_revision=entry.revision,
            event_key=event_key,
            outcome=outcome,
            source_conversation_id=conversation_id,
            captured_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=["journal_entry_id", "rule_revision", "event_key"])
        .returning(JournalEvidenceEvent.id)
    )
    return result.scalar_one_or_none() is not None, conversation_id


async def _lock_current_rule(
    db: AsyncSession, entry: JournalEntry, expected_revision: int
) -> JournalEntry:
    """Refresh under owner/entry locks before any stale ORM field can flush."""
    with db.no_autoflush:
        await lock_journal_owner(db, entry.user_id)
        found = await db.execute(
            select(JournalEntry)
            .where(JournalEntry.id == entry.id, JournalEntry.user_id == entry.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    current: JournalEntry | None = found.scalar_one_or_none()
    if current is None or current.revision != expected_revision:
        raise stale_rule()
    return current


def _changed_values(current: JournalEntry, changes: dict[str, Any]) -> dict[str, Any]:
    """Vectors are prepared writes; scalar fields only change when different."""
    return {
        key: value
        for key, value in changes.items()
        if key in ("embedding", "keyword_embedding") or getattr(current, key) != value
    }


def _retire_validation(
    current: JournalEntry, values: dict[str, Any], evidence_outcome: str | None
) -> None:
    """Changed words or abstraction have a fresh, unvalidated rule revision."""
    values.update(revision=current.revision + 1, evidence_count=0, contradiction_count=0)
    if evidence_outcome:
        logger.debug("journal_old_revision_outcome_ignored", entry_id=str(current.id))


async def _account_reaction(
    db: AsyncSession,
    current: JournalEntry,
    values: dict[str, Any],
    evidence_outcome: str | None,
    event_key: str | None,
    evidence_source: str | None,
) -> tuple[bool, UUID | None, int]:
    """Only a newly claimed event may add one to the stored counter."""
    if evidence_outcome not in ("evidence", "contradiction"):
        return False, None, current.contradiction_count
    counted, source = await record_evidence_event(
        db, current, evidence_outcome, event_key, evidence_source
    )
    if counted:
        field = "evidence_count" if evidence_outcome == "evidence" else "contradiction_count"
        values[field] = getattr(JournalEntry, field) + 1
    contradictions = current.contradiction_count + int(
        counted and evidence_outcome == "contradiction"
    )
    return counted, source, contradictions


async def _certified_evidence(db: AsyncSession, current: JournalEntry) -> int:
    """Legacy totals and whole-answer likes cannot certify a causal rule."""
    result = await db.execute(
        select(func.count())
        .select_from(JournalEvidenceEvent)
        .where(
            JournalEvidenceEvent.journal_entry_id == current.id,
            JournalEvidenceEvent.rule_revision == current.revision,
            JournalEvidenceEvent.outcome == "evidence",
            JournalEvidenceEvent.event_key.not_like(f"{RESPONSE_EVENT_PREFIX}%"),
        )
    )
    count: int = result.scalar_one()
    return count


def _invalidates_portrait(
    values: dict[str, Any],
    replaced: bool,
    counted: bool,
    outcome: str | None,
    old_confidence: str,
    final_confidence: str,
) -> bool:
    """Confirmations preserve words; weaker confidence retires derived certainty."""
    return (
        replaced
        or any(key in values for key in ("theme", "level", "status"))
        or (counted and outcome == "contradiction")
        or (old_confidence != "low" and final_confidence == "low")
        or (old_confidence == "high" and final_confidence == "medium")
    )


async def _persist_update(
    db: AsyncSession, current: JournalEntry, values: dict[str, Any], invalidate_portrait: bool
) -> None:
    """Use SQL arithmetic, then refresh before any later repository flush."""
    with db.no_autoflush:
        await db.execute(
            update(JournalEntry)
            .where(JournalEntry.id == current.id, JournalEntry.revision == current.revision)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await db.refresh(current)
    await mark_journal_changed(db, current.user_id, invalidate_portrait=invalidate_portrait)


async def _record_applied_effects(
    db: AsyncSession,
    current: JournalEntry,
    old_level: str,
    counted: bool,
    source_conversation_id: UUID | None,
    evidence_outcome: str | None,
) -> None:
    """Record only newly applied reactions and actual level transitions."""
    if counted:
        assert evidence_outcome in ("evidence", "contradiction")
        with suppress(Exception):
            journal_evidence_total.labels(outcome=evidence_outcome).inc()
        await record_outcome(
            db,
            user_id=current.user_id,
            journal_entry_id=current.id,
            source=str(source_conversation_id) if source_conversation_id is not None else None,
            evidence_outcome=evidence_outcome,
        )
    if old_level != current.level:
        with suppress(Exception):
            journal_consolidation_promotions_total.labels(
                from_level=old_level, to_level=current.level
            ).inc()


async def apply_update(
    db: AsyncSession,
    entry: JournalEntry,
    changes: dict[str, Any],
    *,
    confidence: str | None,
    evidence_outcome: str | None,
    event_key: str | None,
    evidence_source: str | None,
    expected_revision: int | None,
) -> JournalEntry:
    """Apply a fresh snapshot with SQL arithmetic, never a stale ORM count."""
    expected = expected_revision if expected_revision is not None else entry.revision
    current = await _lock_current_rule(db, entry, expected)
    values = _changed_values(current, changes)
    replaced = any(key in values for key in ("content", "level", "theme"))
    if replaced:
        _retire_validation(current, values, evidence_outcome)
        confidence = "medium"
        counted, source_conversation_id, contradiction_count = False, None, 0
    else:
        counted, source_conversation_id, contradiction_count = await _account_reaction(
            db, current, values, evidence_outcome, event_key, evidence_source
        )
    certified_evidence = 0 if replaced else await _certified_evidence(db, current)
    requested_confidence = confidence if confidence is not None else current.confidence
    final_confidence = clamp_confidence(
        requested_confidence,
        str(values.get("level", current.level)),
        certified_evidence,
        "update",
        contradiction_count,
    )
    if final_confidence != current.confidence:
        values["confidence"] = final_confidence
    if not values:
        return current
    old_level = current.level
    invalidate_portrait = _invalidates_portrait(
        values, replaced, counted, evidence_outcome, current.confidence, final_confidence
    )
    await _persist_update(db, current, values, invalidate_portrait)
    await _record_applied_effects(
        db, current, old_level, counted, source_conversation_id, evidence_outcome
    )
    return current
