"""Reading and writing bounded provenance, without ever copying a source.

Two operations and one invariant:

- ``record`` adds a pointer, CAPPED. A belief reinforced a hundred times does
  not need a hundred rows to be explained; it needs the most recent few and an
  honest count. An unbounded trail would also grow without limit next to data
  that is itself bounded;
- ``resolve`` reads the live source. A reference whose conversation was deleted
  comes back as a TOMBSTONE — dated, sourceless, and carrying no text. That is
  the whole contract: a deletion elsewhere must not be undone here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped

from src.core.constants import PROVENANCE_MAX_REFERENCES_PER_SUBJECT
from src.domains.conversations.models import ConversationMessage
from src.domains.shared.provenance import ProvenanceOutcome, ProvenanceReference
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ResolvedReference:
    """One provenance entry, ready to render.

    Attributes:
        id: The reference row.
        outcome: origin / evidence / contradiction.
        captured_at: When the signal was observed — the ONE fact that survives
            the source being deleted.
        conversation_id: The live conversation, or None once it is gone.
        excerpt: A short quotation of the source turn, read live and capped for
            display. None when there is no live source — a tombstone shows a
            date and says the source is gone, never a remembered copy of it.
    """

    id: uuid.UUID
    outcome: str
    captured_at: datetime
    conversation_id: uuid.UUID | None
    excerpt: str | None

    @property
    def is_tombstone(self) -> bool:
        """True when the source no longer exists."""
        return self.conversation_id is None


class ProvenanceRepository:
    """Bounded provenance for journal entries and memories."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(
        self,
        *,
        user_id: uuid.UUID,
        journal_entry_id: uuid.UUID | None = None,
        memory_id: uuid.UUID | None = None,
        interest_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
        outcome: ProvenanceOutcome = ProvenanceOutcome.ORIGIN,
        captured_at: datetime | None = None,
    ) -> ProvenanceReference | None:
        """Point one belief at one signal, and trim the trail.

        Args:
            user_id: Owner.
            journal_entry_id: The journal entry, when the subject is one.
            memory_id: The memory, when the subject is one.
            interest_id: The interest, when the subject is one.
            conversation_id: Conversation the signal came from.
            message_id: The precise turn, when it is known.
            outcome: What this signal did to the belief.
            captured_at: When it was observed; defaults to the row's own clock.

        Returns:
            The stored reference, or None when the caller supplied no usable
            subject or no source at all — a reference to nothing is a row
            nobody can render, and writing it would only make the trail look
            richer than it is.
        """
        subjects = [
            identifier for identifier in (journal_entry_id, memory_id, interest_id) if identifier
        ]
        if len(subjects) != 1:
            logger.debug("provenance_skipped_no_single_subject", outcome=outcome.value)
            return None
        if conversation_id is None and message_id is None:
            logger.debug("provenance_skipped_no_source", outcome=outcome.value)
            return None

        reference = ProvenanceReference(
            user_id=user_id,
            journal_entry_id=journal_entry_id,
            memory_id=memory_id,
            interest_id=interest_id,
            conversation_id=conversation_id,
            message_id=message_id,
            outcome=outcome.value,
        )
        if captured_at is not None:
            reference.captured_at = captured_at
        self.db.add(reference)
        await self.db.flush()

        await self._trim(
            journal_entry_id=journal_entry_id, memory_id=memory_id, interest_id=interest_id
        )
        return reference

    async def _trim(
        self,
        *,
        journal_entry_id: uuid.UUID | None,
        memory_id: uuid.UUID | None,
        interest_id: uuid.UUID | None = None,
    ) -> None:
        """Keep only the most recent references of one subject.

        Bounded on purpose: a belief reinforced a hundred times is explained by
        its latest handful plus an honest count, not by a hundred rows growing
        beside data that is itself bounded.
        """
        column, value = self._subject(journal_entry_id, memory_id, interest_id)
        keep = (
            select(ProvenanceReference.id)
            .where(column == value)
            .order_by(ProvenanceReference.captured_at.desc(), ProvenanceReference.id.desc())
            .limit(PROVENANCE_MAX_REFERENCES_PER_SUBJECT)
        )
        await self.db.execute(
            delete(ProvenanceReference).where(column == value, ProvenanceReference.id.not_in(keep))
        )

    @staticmethod
    def _subject(
        journal_entry_id: uuid.UUID | None,
        memory_id: uuid.UUID | None,
        interest_id: uuid.UUID | None = None,
    ) -> tuple[Mapped[uuid.UUID | None], uuid.UUID]:
        """The column and value identifying one subject.

        Raises:
            ValueError: No subject given. Stated rather than asserted: `assert`
                is stripped under `python -O`, and the failure would then be an
                unbound name rather than a named contract violation.
        """
        if journal_entry_id is not None:
            return ProvenanceReference.journal_entry_id, journal_entry_id
        if memory_id is not None:
            return ProvenanceReference.memory_id, memory_id
        if interest_id is None:
            raise ValueError("a provenance query needs exactly one subject")
        return ProvenanceReference.interest_id, interest_id

    async def count_for(
        self,
        *,
        journal_entry_id: uuid.UUID | None = None,
        memory_id: uuid.UUID | None = None,
        interest_id: uuid.UUID | None = None,
    ) -> int:
        """Exact number of references kept for one subject."""
        column, value = self._subject(journal_entry_id, memory_id, interest_id)
        stmt = select(func.count()).select_from(ProvenanceReference).where(column == value)
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def resolve_for(
        self,
        *,
        user_id: uuid.UUID,
        journal_entry_id: uuid.UUID | None = None,
        memory_id: uuid.UUID | None = None,
        interest_id: uuid.UUID | None = None,
        excerpt_chars: int = 200,
    ) -> list[ResolvedReference]:
        """Every reference of one subject, newest first, resolved LIVE.

        The excerpt is read from the message as it stands right now and capped
        for display; it is never stored. A reference whose source was deleted
        comes back as a tombstone: dated, sourceless, textless.

        Args:
            user_id: Owner — scopes the read, so a forged subject id from
                another tenant resolves to nothing.
            journal_entry_id: The journal entry, when the subject is one.
            memory_id: The memory, when the subject is one.
            interest_id: The interest, when the subject is one.
            excerpt_chars: How much of the turn to quote.

        Returns:
            The resolved references, newest first.
        """
        column, value = self._subject(journal_entry_id, memory_id, interest_id)
        stmt = (
            select(ProvenanceReference, ConversationMessage.content)
            .outerjoin(
                ConversationMessage, ConversationMessage.id == ProvenanceReference.message_id
            )
            .where(column == value, ProvenanceReference.user_id == user_id)
            .order_by(ProvenanceReference.captured_at.desc(), ProvenanceReference.id.desc())
        )
        resolved: list[ResolvedReference] = []
        for reference, content in (await self.db.execute(stmt)).all():
            # No live conversation → tombstone, whatever the join returned.
            live = reference.conversation_id is not None
            excerpt = None
            if live and content:
                excerpt = content[:excerpt_chars].strip()
            resolved.append(
                ResolvedReference(
                    id=reference.id,
                    outcome=reference.outcome,
                    captured_at=reference.captured_at,
                    conversation_id=reference.conversation_id,
                    excerpt=excerpt,
                )
            )
        return resolved
