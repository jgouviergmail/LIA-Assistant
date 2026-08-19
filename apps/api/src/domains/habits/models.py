"""SQLAlchemy models for the Habits domain (ADR-214).

Models:
- UserHabitProfile: per-user rhythm profile, recomputed nightly (derived data).
- UserHabit: discrete learned habits with feedback signals and user status.

Both tables are registered in the GDPR purge map (``users/user_data_map.py``),
the account deletion service and the account export.
"""

import uuid
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Re-export: ProfileVerdict moved to the pure `verdicts` module (C-04) —
# historical importers (router, schemas, heartbeat) keep working unchanged.
from src.domains.habits.verdicts import ProfileVerdict as ProfileVerdict
from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.users.models import User


class HabitKind(str, Enum):
    """Kind of a learned habit.

    Every mapping keyed by this enum must carry a boot-time completeness
    assert (ADR-085) — a silent fallback on an unknown kind is how features
    die invisibly.
    """

    ACTIVE_WINDOW = "active_window"
    RECURRING_REQUEST = "recurring_request"


class HabitStatus(str, Enum):
    """User-controlled status of a habit.

    - ACTIVE: learned and consumable by proactive surfaces.
    - PAUSED: kept and updated, but never consumed (user snooze).
    - BLOCKED: never relearned for this key (user refusal — the row is the
      tombstone that prevents re-promotion, mirroring blocked interests).
    """

    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"


class UserActivityDay(BaseModel):
    """Durable per-day activity rollup — the rhythm source that survives resets.

    Owner forensics (2026-08-05): the chat "reset" deletes conversation
    messages, and the primary account had 961 resets — raw
    ``conversation_messages`` is NOT a durable activity source for users who
    reset often. This rollup keeps ONLY hour counts (no content, no message
    ids), is merged with per-hour MAX at each recompute (a reset can only
    shrink the live counts, so max preserves the pre-reset truth), and is
    pruned beyond the observation window (~56 rows per user).

    Attributes:
        user_id: Owner.
        local_date: The user's LOCAL calendar date at message time.
        hour_counts: ``{"0".."23": count}`` of human user messages.
    """

    __tablename__ = "user_activity_days"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    hour_counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Per-hour human-message counts for the day (no content).",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "local_date", name="uq_user_activity_days_user_date"),
        Index("ix_user_activity_days_user_date", "user_id", "local_date"),
    )

    def __repr__(self) -> str:
        return f"<UserActivityDay(user_id={self.user_id}, local_date={self.local_date})>"


class UserHabitProfile(BaseModel):
    """Per-user learned rhythm profile (derived, nightly-recomputed).

    The payload is DERIVED data: always recomputable from the conversation
    history, so a deleted conversation naturally leaves the profile at the
    next recompute (right-to-be-forgotten follows the source).

    Attributes:
        user_id: Owner (unique — one profile per user).
        payload: Versioned profile payload (``RhythmProfilePayload`` schema):
            per-class presence histograms, claimed windows, verdicts, meta.
        computed_at: When the nightly job last recomputed this profile.
        source_max_created_at: ``max(created_at)`` of the user messages the
            profile was computed from — the delta-skip marker (a user with no
            new messages costs nothing on the next run).
    """

    __tablename__ = "user_habit_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Versioned rhythm profile (histograms, windows, verdicts).",
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source_max_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Delta-skip marker: newest source message the profile saw.",
    )

    user: Mapped["User"] = relationship()

    def __repr__(self) -> str:
        return f"<UserHabitProfile(user_id={self.user_id}, computed_at={self.computed_at})>"


class UserHabit(BaseModel):
    """One discrete learned habit, user-controllable end to end.

    Mirrors ``UserInterest``: Bayesian feedback signals, explicit status,
    uniqueness per (user, kind, key). The payload is a versioned Pydantic
    schema per kind (``ActiveWindowPayload`` / ``RecurringRequestPayload``)
    — round-trip tested, msgpack/JSONB safe.

    Attributes:
        user_id: Owner.
        kind: ``HabitKind`` value.
        key: Stable identity of the habit within its kind (e.g.
            ``"weekday:8-10"`` or the recurrence signature ``"email"``).
        payload: Kind-specific payload (schema versioned).
        positive_signals: Feedback ramp-up (accepted offer, thumbs up).
        negative_signals: Feedback ramp-down (dismissed offer, thumbs down,
            implicit non-uptake of deviation offers).
        status: ``HabitStatus`` value — BLOCKED rows are tombstones that
            prevent relearning of the key.
        last_observed_at: Last time the underlying behaviour was seen.
        muted_until_reproof: Deviation stop-rule marker — after 2 consecutive
            ignored offers the type-1 remark goes silent for this habit until
            a fresh positive occurrence resets it.
    """

    __tablename__ = "user_habits"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Kind-specific versioned payload (windows / schedule shape).",
    )

    positive_signals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_signals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=HabitStatus.ACTIVE.value,
    )

    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    muted_until_reproof: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Deviation stop-rule: type-1 offers muted until re-occurrence.",
    )

    user: Mapped["User"] = relationship()

    __table_args__ = (
        UniqueConstraint("user_id", "kind", "key", name="uq_user_habits_user_kind_key"),
        Index("ix_user_habits_user_kind", "user_id", "kind"),
        Index("ix_user_habits_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<UserHabit(id={self.id}, kind={self.kind}, key='{self.key}', status={self.status})>"
        )
