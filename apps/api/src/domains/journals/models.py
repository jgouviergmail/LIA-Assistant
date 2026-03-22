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
    from src.domains.auth.models import User


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
        source: Origin (conversation extraction / periodic consolidation / manual)
        session_id: Conversation session that triggered extraction (nullable)
        personality_code: Personality code active when entry was written (nullable)
        char_count: Content character count (for size tracking)
        embedding: OpenAI text-embedding-3-small (1536 dims) for semantic relevance search
        search_hints: LLM-generated keywords bridging user vocabulary to entry content
        injection_count: Number of times this entry was injected into prompts
        last_injected_at: Last time this entry was injected into a prompt (UTC)
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

    # Embedding for semantic relevance search (1536 dims for OpenAI text-embedding-3-small)
    embedding: Mapped[list[float] | None] = mapped_column(
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
