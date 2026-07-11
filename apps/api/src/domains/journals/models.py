"""
SQLAlchemy models for the Journals domain.

Models:
- JournalEntry: Assistant's personal logbook entries with semantic embeddings

Enums:
- JournalTheme: Thematic categories for journal entries
- JournalEntryMood: Emotional tone of an entry
- JournalEntryStatus: Lifecycle status (active/archived)
- JournalEntrySource: Origin of the entry (conversation/consolidation/manual)
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domains.journals.constants import JOURNAL_EMBEDDING_DIMENSIONS
from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.users.models import User


class JournalTheme(str, Enum):
    """Thematic category for journal entries."""

    SELF_REFLECTION = "self_reflection"
    USER_OBSERVATIONS = "user_observations"
    IDEAS_ANALYSES = "ideas_analyses"
    LEARNINGS = "learnings"


class JournalEntryMood(str, Enum):
    """Emotional tone of a journal entry."""

    REFLECTIVE = "reflective"
    CURIOUS = "curious"
    SATISFIED = "satisfied"
    CONCERNED = "concerned"
    INSPIRED = "inspired"


class JournalEntryStatus(str, Enum):
    """Lifecycle status of a journal entry."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class JournalEntrySource(str, Enum):
    """Origin of a journal entry."""

    CONVERSATION = "conversation"
    CONSOLIDATION = "consolidation"
    MANUAL = "manual"
    USER_CORRECTION = "user_correction"


class JournalEntryConfidence(str, Enum):
    """Epistemic status of a journal entry.

    Distinguishes hypotheses from validated directives so the assistant
    can avoid auto-reinforcing confirmation loops. Confidence transitions
    are LLM-driven during consolidation, based on the visible
    ``evidence_count`` and ``contradiction_count`` metrics.
    """

    LOW = "low"  # Hypothesis — single observation, not yet verified
    MEDIUM = "medium"  # Default — observed but not strongly validated
    HIGH = "high"  # Validated — confirmed by repeated evidence


class JournalEntryLevel(str, Enum):
    """Abstraction level of a journal entry — the cognitive stratification.

    The four levels form a hierarchy of increasing abstraction. Each level
    has its own role and lifecycle. Lower levels feed the upper ones via
    LLM-driven promotion during consolidation.

    - L0 (observations): raw signals, contradictions, reception cues. Open text,
      ephemeral. Promoted to L1 if recurrent, else pruned.
    - L1 (directives): WHEN→DO BECAUSE — the operational format inherited from
      ADR-064. Validated/invalidated by deferred self-evaluation. Promoted to L2
      when convergent with siblings.
    - L2 (patterns): transversal syntheses across multiple L1 directives. Stable,
      narrative. Refunded at consolidation.
    - L3 (portrait): facets of the user model — traits, current phase, contexts,
      contradictions, blind spots, evolution. Always-injected (compiled in commit 3).
    """

    L0 = "L0"  # Raw observations
    L1 = "L1"  # Operational directives (the legacy format)
    L2 = "L2"  # Transversal patterns
    L3 = "L3"  # User model facets


class JournalEntry(BaseModel):
    """
    Assistant's personal logbook entry.

    Stores the assistant's own reflections, observations, analyses and
    learnings. Entries are written from the assistant's perspective,
    colored by its active personality, and influence future responses
    via semantic context injection.

    Attributes:
        user_id: Owner user (entries are per-user)
        theme: Thematic category (self_reflection, user_observations, etc.)
        title: Short descriptive title
        content: Full entry content (assistant's writing)
        mood: Emotional tone when writing
        status: Lifecycle status (active/archived)
        source: Origin (conversation extraction / periodic consolidation / manual / user_correction)
        session_id: Conversation session that triggered extraction (nullable)
        personality_code: Personality code active when entry was written (nullable)
        char_count: Content character count (for size tracking)
        embedding: Gemini gemini-embedding-001 (1536 dims) for semantic relevance search
        search_hints: LLM-generated keywords bridging user vocabulary to entry content
        injection_count: Number of times this entry was injected into prompts
        last_injected_at: Last time this entry was injected into a prompt (UTC)
        confidence: Epistemic status (low/medium/high) — distinguishes hypothesis from
            validated directive. Defaults to medium for backward compatibility.
        evidence_count: Counter incremented when deferred self-evaluation confirms the
            entry by observing the user's reaction at the next turn.
        contradiction_count: Counter incremented when deferred self-evaluation invalidates
            the entry by observing reformulation, pushback or correction at the next turn.
        level: Abstraction level (L0/L1/L2/L3) — defaults to L1 for legacy entries.
    """

    __tablename__ = "journal_entries"

    # Foreign key
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Entry content
    theme: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
    )
    mood: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=JournalEntryMood.REFLECTIVE.value,
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=JournalEntryStatus.ACTIVE.value,
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=JournalEntrySource.CONVERSATION.value,
    )

    # Traceability
    session_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    personality_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Size tracking (for prompt-driven lifecycle management)
    char_count: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=0,
    )

    # Semantic embeddings (Gemini gemini-embedding-001: 1536 dims)
    # embedding: title+content (main semantic match)
    # keyword_embedding: search_hints keywords only (keyword-level match)
    # Search uses LEAST(dist_content, dist_keyword) for best match.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(JOURNAL_EMBEDDING_DIMENSIONS),
        nullable=True,
    )
    keyword_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(JOURNAL_EMBEDDING_DIMENSIONS),
        nullable=True,
    )

    # LLM-generated search keywords bridging user vocabulary to entry content
    search_hints: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(100)),
        nullable=True,
    )

    # Injection tracking (feedback loop for consolidation optimization)
    injection_count: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=0,
        server_default="0",
    )
    last_injected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Epistemic status — distinguishes hypotheses from validated directives.
    # Updated by deferred self-evaluation (T → T+1) via LLM-driven actions.
    confidence: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=JournalEntryConfidence.MEDIUM.value,
        server_default=JournalEntryConfidence.MEDIUM.value,
    )
    evidence_count: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=0,
        server_default="0",
    )
    contradiction_count: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=0,
        server_default="0",
    )

    # Cognitive stratification (commit 2 of journal-conscience-operationnelle)
    # L0 raw observations / L1 directives / L2 patterns / L3 portrait facets.
    # Defaults to L1 — preserves the semantics of legacy entries without backfill.
    level: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        default=JournalEntryLevel.L1.value,
        server_default=JournalEntryLevel.L1.value,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="journal_entries")

    # Indexes for efficient queries
    __table_args__ = (
        Index(
            "ix_journal_entries_user_status_created",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_journal_entries_user_theme",
            "user_id",
            "theme",
        ),
    )

    def __repr__(self) -> str:
        title_preview = self.title[:30] if self.title else ""
        return (
            f"<JournalEntry(id={self.id}, theme='{self.theme}', "
            f"title='{title_preview}...', status={self.status})>"
        )
