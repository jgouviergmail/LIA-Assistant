"""Where a belief came from — as a BOUNDED reference, never as a copy.

A journal entry says "prefers written summaries over calls"; a memory says
"allergic to shellfish". Both are conclusions LIA drew, both are injected into
prompts, and until now neither could answer the only question that makes them
correctable: *why do you think that?*

The material existed and was thrown away. Journal entries carry
``evidence_count`` and ``contradiction_count`` — pure counters — while the
deferred self-evaluation (ADR-079) knows, at the moment it increments one,
exactly which turn produced the signal (`injected_journal_ids` in the graph
state). Memories carried nothing at all, though the extractor receives both a
session id and a conversation id.

**What is stored is a POINTER and a timestamp, never the words.** A reference
that copied the message would be a second, permanent home for content the user
can delete elsewhere — the deletion would stop being a deletion. So:

- the source columns are real foreign keys with ``ON DELETE SET NULL``: when a
  conversation goes, the pointer goes with it and the row REMAINS, dated. That
  row is the tombstone. It states that something supported this belief and that
  the something is gone;
- resolving a reference reads the live source. A resolved reference shows what
  the source says NOW; an unresolvable one shows when it was captured and
  nothing else. Neither ever resurrects deleted content.

One row belongs to exactly one subject and points at exactly one source, both
enforced by CHECK constraints rather than by convention: a polymorphic
``(kind, id)`` pair cannot be a foreign key, and without a foreign key the
tombstone above is not guaranteed by anything.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class ProvenanceOutcome(str, Enum):
    """What this reference DID to the belief it points at.

    Distinguishing them is the whole point of showing provenance: "this is
    where it came from" and "this is what later contradicted it" are different
    answers, and a reader deciding whether to correct an entry needs both.
    """

    ORIGIN = "origin"  # The turn the belief was extracted from.
    EVIDENCE = "evidence"  # A later turn that confirmed it.
    CONTRADICTION = "contradiction"  # A later turn that went against it.


class ProvenanceReference(BaseModel):
    """One bounded pointer from a belief to the signal behind it.

    Attributes:
        user_id: Owner. Scopes every read; a reference is never cross-tenant.
        journal_entry_id: The journal entry this supports, or None.
        memory_id: The memory this supports, or None.
        interest_id: The interest this supports, or None. An interest IS a
            belief LIA formed — "you seem to care about X" — so it belongs
            here rather than in a column of its own. Exactly one of the three
            subjects is set: CHECK-enforced, because a reference to nothing is
            a row nobody can render and a reference to two is a row nobody can
            interpret.
        conversation_id: The conversation the signal came from. NULLED when
            that conversation is deleted, which is what turns this row into a
            tombstone rather than a dangling pointer or a resurrection.
        message_id: The precise turn, when it is known. Same nulling rule.
        outcome: origin / evidence / contradiction.
        captured_at: When the signal was observed. Survives the nulling above,
            so a tombstone can still say WHEN — the one fact that does not
            depend on the source still existing.
    """

    __tablename__ = "provenance_references"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=True,
    )
    memory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memories.id", ondelete="CASCADE"),
        nullable=True,
    )
    interest_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_interests.id", ondelete="CASCADE"),
        nullable=True,
    )

    # SET NULL, never CASCADE: deleting the conversation must not delete the
    # trace that a belief once rested on it. The row left behind is the
    # tombstone the product promises.
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation_messages.id", ondelete="SET NULL"),
        nullable=True,
    )

    outcome: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ProvenanceOutcome.ORIGIN.value,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        CheckConstraint(
            "(journal_entry_id IS NOT NULL)::int + (memory_id IS NOT NULL)::int"
            " + (interest_id IS NOT NULL)::int = 1",
            name="ck_provenance_exactly_one_subject",
        ),
        Index("ix_provenance_journal_entry", "journal_entry_id", "captured_at"),
        Index("ix_provenance_memory", "memory_id", "captured_at"),
        Index("ix_provenance_interest", "interest_id", "captured_at"),
        Index("ix_provenance_user", "user_id"),
    )

    def __repr__(self) -> str:
        subject = self.journal_entry_id or self.memory_id or self.interest_id
        return f"<ProvenanceReference(subject={subject}, outcome={self.outcome})>"
