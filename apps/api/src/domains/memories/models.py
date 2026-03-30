"""
SQLAlchemy models for the Memories domain.

Models:
- Memory: Long-term user memory with pgvector semantic embedding

Enums:
- MemoryCategory: Memory classification categories (6 types)

Replaces LangGraph AsyncPostgresStore for memory storage. The store
remains in use for tool context, heartbeat context, and future documents.

Phase: v1.14.0 — Memory migration to PostgreSQL custom
Created: 2026-03-30
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.auth.models import User


# Embedding dimensions: OpenAI text-embedding-3-small
MEMORY_EMBEDDING_DIMENSIONS = 1536


class MemoryCategory(str, Enum):
    """Classification categories for user memories.

    Categories determine how memories are prioritized in the psychological
    profile and influence the emotional state computation:
    - sensitivity: Highest priority (trauma, pain, conflicts)
    - relationship: People and connections
    - preference: Likes, dislikes, tastes
    - personal: Identity, job, location
    - pattern: Recurring behaviors, habits
    - event: Significant past or future events
    """

    PREFERENCE = "preference"
    PERSONAL = "personal"
    RELATIONSHIP = "relationship"
    EVENT = "event"
    PATTERN = "pattern"
    SENSITIVITY = "sensitivity"


class Memory(BaseModel):
    """Long-term user memory with semantic embedding.

    Stores factual information about the user extracted from conversations
    by the memory extraction pipeline. Memories are formulated in first
    person (user's perspective) for optimal semantic search matching.

    Semantic search via pgvector cosine distance enables:
    - Injection: relevant memories added to response/planner prompts
    - Extraction dedup: avoid creating duplicate memories
    - Reference resolution: "my wife" → "Jane Smith" via relationship memories

    Attributes:
        user_id: Owner user (memories are per-user, isolated by FK)
        content: Memory text in first person (max 500 chars, atomic fact)
        category: Classification type (preference, personal, relationship, etc.)
        emotional_weight: Emotional intensity (-10 trauma to +10 joy)
        trigger_topic: Keyword that activates this memory in search
        usage_nuance: Guidance for how the assistant should use this info
        importance: Absolute importance score (0.0 to 1.0)
        usage_count: Times retrieved with high relevance (Phase 6 tracking)
        last_accessed_at: Last high-relevance retrieval timestamp
        pinned: Protected from automatic purge (user-controlled)
        embedding: pgvector 1536-dim for cosine distance search
        char_count: Content length for statistics
    """

    __tablename__ = "memories"

    # Foreign key
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Content (atomic fact, max 500 chars, first-person formulation)
    content: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # Qualification
    emotional_weight: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=0,
        server_default="0",
    )
    trigger_topic: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        server_default="",
    )
    usage_nuance: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
        default="",
        server_default="",
    )
    importance: Mapped[float] = mapped_column(
        Float(),
        nullable=False,
        default=0.7,
        server_default="0.7",
    )

    # Phase 6: Lifecycle tracking
    usage_count: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=0,
        server_default="0",
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    pinned: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default="false",
    )

    # Semantic embedding (OpenAI text-embedding-3-small: 1536 dims)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(MEMORY_EMBEDDING_DIMENSIONS),
        nullable=True,
    )

    # Size tracking
    char_count: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=0,
        server_default="0",
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="memories")

    # Indexes for efficient queries
    __table_args__ = (
        Index(
            "ix_memories_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_memories_user_category",
            "user_id",
            "category",
        ),
    )

    def __repr__(self) -> str:
        content_preview = self.content[:40] if self.content else ""
        return (
            f"<Memory(id={self.id}, category='{self.category}', "
            f"content='{content_preview}...', importance={self.importance})>"
        )
