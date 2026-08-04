"""Recording provenance from an extraction, for any belief LIA forms.

Journals and memories are extracted by two different services, from the same
material, and both need the same three things: read a session/conversation
identifier that is stored as a bare string, write a BOUNDED pointer, and never
let that write break the extraction it describes. Two copies of those three
things is one copy too many — the second is where a rule quietly goes missing.

Two properties hold for everything here:

- **best-effort, and isolated**: provenance EXPLAINS a belief, it never gates
  one. A failure must not roll back an extraction that succeeded — the belief is
  still true, it is merely harder to question. Swallowing the exception is NOT
  enough to deliver that: a failed ``flush`` leaves the session in a failed
  state, so the very next statement raises ``PendingRollbackError`` and the
  extraction dies anyway, from a second error, with the first already hidden.
  Every write is therefore scoped to a SAVEPOINT (``begin_nested``, the pattern
  ``conversations/service.py`` already uses): the inner failure rolls back to
  the savepoint and the outer transaction survives intact;
- **bounded**: what is written is a pointer and a timestamp. The words stay
  where the user put them, so a deletion there is a deletion everywhere.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING
from uuid import UUID

from src.domains.shared.provenance import ProvenanceOutcome
from src.domains.shared.provenance_repository import ProvenanceRepository
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

#: Outcomes a caller may record for an already-formed belief. `origin` is
#: excluded on purpose: it is written once, by `record_origin`, and a second
#: origin for the same belief would be a claim nobody could arbitrate.
_REEVALUATION_OUTCOMES = frozenset(
    {ProvenanceOutcome.EVIDENCE.value, ProvenanceOutcome.CONTRADICTION.value}
)


def conversation_id_of(value: str | None) -> UUID | None:
    """Read a stored identifier as the conversation it names.

    Both ``JournalEntry.session_id`` and the memory extractor's
    ``conversation_id`` are plain strings with no foreign key behind them —
    verified on the production database, every non-null journal value joins a
    conversation row. Parsed rather than trusted, precisely because nothing at
    the schema level guarantees it.

    Args:
        value: The stored identifier.

    Returns:
        The conversation id, or None when the value cannot be one.
    """
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        logger.debug("provenance_source_not_a_uuid")
        return None


async def record_origin(
    db: AsyncSession,
    *,
    user_id: UUID,
    source: str | None,
    journal_entry_id: UUID | None = None,
    memory_id: UUID | None = None,
    interest_id: UUID | None = None,
) -> None:
    """Point a freshly extracted belief at the conversation it came from.

    Args:
        db: The session the extraction already owns.
        user_id: Owner.
        source: The conversation identifier, as the extractor holds it.
        journal_entry_id: The entry, when the belief is one.
        memory_id: The memory, when the belief is one.
        interest_id: The interest, when the belief is one.
    """
    conversation_id = conversation_id_of(source)
    if conversation_id is None:
        return
    # The savepoint is what makes the swallow honest: without it the caller
    # keeps a poisoned session and fails on its NEXT statement instead.
    with suppress(Exception):
        async with db.begin_nested():
            await ProvenanceRepository(db).record(
                user_id=user_id,
                journal_entry_id=journal_entry_id,
                memory_id=memory_id,
                interest_id=interest_id,
                conversation_id=conversation_id,
            )


async def record_outcome(
    db: AsyncSession,
    *,
    user_id: UUID,
    source: str | None,
    evidence_outcome: str,
    journal_entry_id: UUID | None = None,
    memory_id: UUID | None = None,
    interest_id: UUID | None = None,
) -> None:
    """Record the turn that CONFIRMED or CONTRADICTED an existing belief.

    The deferred self-evaluation (ADR-079) already knew this at the instant it
    incremented ``evidence_count`` / ``contradiction_count``, and threw it away
    — leaving two counters nobody could question. "Three things confirmed it"
    is not an explanation; "this turn, on that day" is.

    Args:
        db: The session the caller owns.
        user_id: Owner.
        source: The conversation of the CURRENT turn — the one that produced
            the signal, not the one the belief came from.
        evidence_outcome: ``evidence`` or ``contradiction``. Anything else is
            ignored rather than stored as a third, undefined kind.
        journal_entry_id: The entry, when the belief is one.
        memory_id: The memory, when the belief is one.
        interest_id: The interest, when the belief is one.
    """
    if evidence_outcome not in _REEVALUATION_OUTCOMES:
        return
    conversation_id = conversation_id_of(source)
    if conversation_id is None:
        return
    # The savepoint is what makes the swallow honest: without it the caller
    # keeps a poisoned session and fails on its NEXT statement instead.
    with suppress(Exception):
        async with db.begin_nested():
            await ProvenanceRepository(db).record(
                user_id=user_id,
                journal_entry_id=journal_entry_id,
                memory_id=memory_id,
                interest_id=interest_id,
                conversation_id=conversation_id,
                outcome=ProvenanceOutcome(evidence_outcome),
            )
