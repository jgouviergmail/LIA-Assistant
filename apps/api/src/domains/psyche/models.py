"""
Psyche domain database models.

Defines the persistence layer for the AI assistant's psychological state:
- PsycheState: 1:1 with users, stores all dynamic mood/emotion/relationship data
- PsycheHistory: Many per user, stores evolution snapshots for tracking

Phase: evolution — Psyche Engine (Iteration 1)
Created: 2026-04-01
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domains.psyche.constants import PSYCHE_SCHEMA_VERSION
from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.auth.models import User


class PsycheState(BaseModel):
    """Dynamic psychological state for one user (1:1 relationship).

    Stores the complete internal state of the AI assistant's psyche
    for a given user: personality traits, mood (PAD space), active emotions,
    relationship metrics, self-efficacy, and drives.

    Updated on every non-trivial interaction via PsycheService.
    Cached in Redis for fast pre-response loading.
    """

    __tablename__ = "psyche_states"

    # Foreign key — unique enforces 1:1
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # =========================================================================
    # Big Five personality traits [0.0, 1.0]
    # Initialized from personality on first creation, evolves independently.
    # =========================================================================
    trait_openness: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    trait_conscientiousness: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    trait_extraversion: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    trait_agreeableness: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    trait_neuroticism: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    # =========================================================================
    # Mood in PAD space [-1.0, +1.0]
    # Decays toward personality-defined baseline. Updated by emotions.
    # =========================================================================
    mood_pleasure: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mood_arousal: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mood_dominance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mood_quadrant_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When mood entered current PAD quadrant (for inertia calculation).",
    )

    # =========================================================================
    # Active emotions (JSONB list)
    # Each entry: {"name": str, "intensity": float, "triggered_at": ISO8601}
    # =========================================================================
    active_emotions: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="Active emotions with intensity and timestamp.",
    )

    # =========================================================================
    # Self-efficacy per domain (JSONB dict)
    # Each entry: {"domain_name": {"score": float, "weight": float}}
    # =========================================================================
    self_efficacy: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Bayesian self-efficacy scores per domain.",
    )

    # =========================================================================
    # Relationship tracking
    # =========================================================================
    relationship_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ORIENTATION",
        comment="Current relationship stage: ORIENTATION, EXPLORATORY, AFFECTIVE, STABLE.",
    )
    relationship_depth: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Relationship depth [0, 1], monotonically increasing.",
    )
    relationship_warmth_active: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, comment="Active warmth [0, 1], decays with absence."
    )
    relationship_trust: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.3, comment="Accumulated trust [0, 1], Bayesian updates."
    )
    relationship_interaction_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Total non-trivial interaction count."
    )
    relationship_total_duration_minutes: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Estimated total interaction duration (minutes).",
    )
    relationship_last_interaction: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last non-trivial interaction.",
    )

    # =========================================================================
    # Drives
    # =========================================================================
    drive_curiosity: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, comment="Curiosity drive [0, 1]."
    )
    drive_engagement: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, comment="Engagement/flow drive [0, 1]."
    )

    # =========================================================================
    # Metadata
    # =========================================================================
    last_appraisal: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Last parsed psyche_eval appraisal result.",
    )
    narrative_identity: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="AI's self-narrative text (generated monthly, Iteration 5).",
    )
    psyche_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=PSYCHE_SCHEMA_VERSION,
        comment="Schema version for forward/backward compatibility.",
    )

    # =========================================================================
    # Relationship to User
    # =========================================================================
    user: Mapped[User] = relationship(back_populates="psyche_state")

    # NOTE: user_id has unique=True on column definition — no need for
    # separate UniqueConstraint in __table_args__. The migration creates
    # the constraint explicitly via op.create_unique_constraint().

    def __repr__(self) -> str:
        """Concise representation for logging."""
        return (
            f"<PsycheState(user_id={self.user_id}, "
            f"mood=P{self.mood_pleasure:.2f}/A{self.mood_arousal:.2f}/D{self.mood_dominance:.2f}, "
            f"stage={self.relationship_stage})>"
        )


class PsycheHistory(BaseModel):
    """Psyche evolution snapshot for tracking personality growth over time.

    Recorded after each message, at session end, daily, or during weekly reflection.
    Used for the emotional evolution dashboard and trait evolution analysis.
    """

    __tablename__ = "psyche_history"

    # Foreign key
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Snapshot metadata
    snapshot_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Snapshot type: message, session_end, daily, weekly_reflection, reset_soft, reset_full.",
    )

    # PAD mood at snapshot time
    mood_pleasure: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mood_arousal: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mood_dominance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Dominant emotion at snapshot time
    dominant_emotion: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="Dominant active emotion at snapshot time.",
    )

    # Relationship stage
    relationship_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ORIENTATION",
    )

    # Big Five traits snapshot (JSONB for flexibility)
    trait_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Big Five trait values at snapshot time.",
    )

    # =========================================================================
    # Table configuration
    # =========================================================================
    __table_args__ = (Index("ix_psyche_history_user_created", "user_id", "created_at"),)

    def __repr__(self) -> str:
        """Concise representation for logging."""
        return (
            f"<PsycheHistory(user_id={self.user_id}, "
            f"type={self.snapshot_type}, "
            f"mood=P{self.mood_pleasure:.2f})>"
        )
