"""Conservative merging of equivalent rules without inventing evidence.

Only current-rule events can be unioned. A source carrying events about a
retired proposition cannot be deleted until it has a lossless archive path.
Legacy counters are retained as descriptive totals, never certified as
independent reactions by adding duplicate records together.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from src.core.constants import PROVENANCE_MAX_REFERENCES_PER_SUBJECT
from src.core.exceptions import ResourceConflictError
from src.domains.journals.evidence import RESPONSE_EVENT_PREFIX, clamp_confidence, stale_rule
from src.domains.journals.evidence_models import JournalEvidenceEvent
from src.domains.journals.lifecycle import lock_journal_owner, mark_journal_changed
from src.domains.journals.models import JournalEntry
from src.domains.shared.provenance import ProvenanceReference

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def normalized_rule(content: str) -> str:
    """Ignore outer whitespace only; never infer equivalence of instructions."""
    return content.strip()


def union_hints(entries: list[JournalEntry]) -> list[str]:
    """Keep the winner's vocabulary and every distinct source hint."""
    return list(dict.fromkeys(hint for entry in entries for hint in (entry.search_hints or [])))


async def _lock_merge_rules(
    db: AsyncSession,
    winner: JournalEntry,
    source_ids: list[UUID],
    expected_revisions: dict[str, int],
) -> list[JournalEntry]:
    """Refresh every source under the same owner-first lock and CAS fence."""
    with db.no_autoflush:
        await lock_journal_owner(db, winner.user_id)
        result = await db.execute(
            select(JournalEntry)
            .where(
                JournalEntry.id.in_([winner.id, *source_ids]),
                JournalEntry.user_id == winner.user_id,
            )
            .order_by(JournalEntry.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    by_id = {entry.id: entry for entry in result.scalars().all()}
    if len(by_id) != len(source_ids) + 1:
        raise stale_rule()
    current = by_id[winner.id]
    sources = [by_id[identifier] for identifier in source_ids]
    entries = [current, *sources]
    if any(expected_revisions.get(str(entry.id)) != entry.revision for entry in entries):
        raise stale_rule()
    return entries


def _compatible_hints(entries: list[JournalEntry], prepared_hints: list[str]) -> list[str]:
    """Transfer validation only between the same words and abstraction."""
    current, *sources = entries
    if any(
        normalized_rule(entry.content) != normalized_rule(current.content)
        or entry.level != current.level
        or entry.theme != current.theme
        for entry in sources
    ):
        raise ResourceConflictError(
            "journal_entry", detail={"error_code": "INCOMPATIBLE_JOURNAL_RULES"}
        )
    hints = union_hints(entries)
    if hints != prepared_hints:
        raise stale_rule()
    return hints


async def _check_provenance_budget(db: AsyncSession, entry_ids: list[UUID]) -> None:
    """An over-budget transfer must refuse rather than silently lose traces."""
    references = (
        await db.execute(
            select(func.count())
            .select_from(ProvenanceReference)
            .where(ProvenanceReference.journal_entry_id.in_(entry_ids))
        )
    ).scalar_one()
    if references > PROVENANCE_MAX_REFERENCES_PER_SUBJECT:
        raise ResourceConflictError(
            "journal_entry", detail={"error_code": "JOURNAL_MERGE_PROVENANCE_BUDGET"}
        )


async def _current_events(
    db: AsyncSession, entries: list[JournalEntry], source_ids: list[UUID]
) -> list[JournalEvidenceEvent]:
    """Loser history must remain intact until a lossless archive path exists."""
    by_id = {entry.id: entry for entry in entries}
    events = list(
        (
            await db.execute(
                select(JournalEvidenceEvent).where(JournalEvidenceEvent.journal_entry_id.in_(by_id))
            )
        )
        .scalars()
        .all()
    )
    if any(
        event.journal_entry_id in source_ids
        and event.rule_revision != by_id[event.journal_entry_id].revision
        for event in events
    ):
        raise ResourceConflictError(
            "journal_entry", detail={"error_code": "JOURNAL_MERGE_RETIRED_EVIDENCE"}
        )
    return [
        event for event in events if event.rule_revision == by_id[event.journal_entry_id].revision
    ]


def _union_events(events: list[JournalEvidenceEvent]) -> dict[str, JournalEvidenceEvent]:
    """Deduplicate deterministic source keys; a contradiction takes precedence."""
    union: dict[str, JournalEvidenceEvent] = {}
    for event in sorted(events, key=lambda item: (item.captured_at, str(item.id))):
        previous = union.get(event.event_key)
        if previous is None or (
            previous.outcome != "contradiction" and event.outcome == "contradiction"
        ):
            union[event.event_key] = event
    return union


def _legacy_totals(
    entries: list[JournalEntry], events: list[JournalEvidenceEvent]
) -> tuple[int, int]:
    """Unknown legacy independence remains descriptive, never certification."""
    legacy_evidence = legacy_contradictions = 0
    for entry in entries:
        known = [event for event in events if event.journal_entry_id == entry.id]
        legacy_evidence += max(
            0, entry.evidence_count - sum(event.outcome == "evidence" for event in known)
        )
        legacy_contradictions += max(
            0, entry.contradiction_count - sum(event.outcome == "contradiction" for event in known)
        )
    return legacy_evidence, legacy_contradictions


def _evidence_values(
    entries: list[JournalEntry],
    events: list[JournalEvidenceEvent],
    union: dict[str, JournalEvidenceEvent],
) -> dict[str, Any]:
    """Keep all descriptive reactions while certifying only current causal ones."""
    legacy_evidence, legacy_contradictions = _legacy_totals(entries, events)
    distinct_evidence = sum(event.outcome == "evidence" for event in union.values())
    certified_evidence = sum(
        event.outcome == "evidence" and not event.event_key.startswith(RESPONSE_EVENT_PREFIX)
        for event in union.values()
    )
    evidence = legacy_evidence + distinct_evidence
    contradictions = legacy_contradictions + sum(
        event.outcome == "contradiction" for event in union.values()
    )
    confidence = max(
        (entry.confidence for entry in entries),
        key=lambda value: {"low": 0, "medium": 1, "high": 2}[value],
    )
    confidence = clamp_confidence(
        confidence, entries[0].level, certified_evidence, "update", contradictions
    )
    return {
        "evidence_count": evidence,
        "contradiction_count": contradictions,
        "confidence": confidence,
    }


async def _replace_current_events(
    db: AsyncSession, current: JournalEntry, union: dict[str, JournalEvidenceEvent]
) -> None:
    """Replace only the winner's current ledger; retired winner events survive."""
    await db.execute(
        delete(JournalEvidenceEvent).where(
            JournalEvidenceEvent.journal_entry_id == current.id,
            JournalEvidenceEvent.rule_revision == current.revision,
        )
    )
    if union:
        await db.execute(
            insert(JournalEvidenceEvent),
            [
                {
                    "id": uuid4(),
                    "user_id": current.user_id,
                    "journal_entry_id": current.id,
                    "rule_revision": current.revision,
                    "event_key": event.event_key,
                    "outcome": event.outcome,
                    "source_conversation_id": event.source_conversation_id,
                    "captured_at": event.captured_at,
                }
                for event in union.values()
            ],
        )


async def _write_merged_rule(
    db: AsyncSession,
    current: JournalEntry,
    sources: list[UUID],
    entries: list[JournalEntry],
    values: dict[str, Any],
    hints: list[str],
    keyword_embedding: list[float] | None,
) -> None:
    """Transfer every trace before loser CASCADE, then persist union statistics."""
    # Transfer every bounded trace before source-entry CASCADE can remove it.
    await db.execute(
        update(ProvenanceReference)
        .where(ProvenanceReference.journal_entry_id.in_(sources))
        .values(journal_entry_id=current.id)
        .execution_options(synchronize_session=False)
    )
    last_injected = [
        entry.last_injected_at for entry in entries if entry.last_injected_at is not None
    ]
    await db.execute(
        update(JournalEntry)
        .where(JournalEntry.id == current.id)
        .values(
            **values,
            search_hints=hints or None,
            keyword_embedding=keyword_embedding,
            injection_count=sum(entry.injection_count for entry in entries),
            last_injected_at=max(last_injected) if last_injected else None,
        )
        .execution_options(synchronize_session=False)
    )
    await db.execute(
        delete(JournalEntry)
        .where(JournalEntry.id.in_(sources))
        .execution_options(synchronize_session=False)
    )
    await db.refresh(current)
    await mark_journal_changed(db, current.user_id)


async def merge_entries(
    db: AsyncSession,
    winner: JournalEntry,
    source_ids: list[UUID],
    expected_revisions: dict[str, int],
    *,
    prepared_hints: list[str],
    keyword_embedding: list[float] | None,
) -> JournalEntry:
    """Apply an ownership/revision-checked merge as one caller transaction."""
    source_ids = sorted(set(source_ids) - {winner.id})
    if not source_ids:
        return winner
    entries = await _lock_merge_rules(db, winner, source_ids, expected_revisions)
    current = entries[0]
    hints = _compatible_hints(entries, prepared_hints)
    await _check_provenance_budget(db, [entry.id for entry in entries])
    events = await _current_events(db, entries, source_ids)
    union = _union_events(events)
    values = _evidence_values(entries, events, union)
    await _replace_current_events(db, current, union)
    await _write_merged_rule(db, current, source_ids, entries, values, hints, keyword_embedding)
    return current
