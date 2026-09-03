"""Pydantic schemas for the Habits API (ADR-214).

Structured data + stable enum values; labels are resolved client-side from
the locale files (never pre-translated strings baked into payloads).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.habits.models import HabitKind, HabitStatus, ProfileVerdict


class HabitWindowSchema(BaseModel):
    """One claimed active window (local hours, wrap-aware)."""

    start_hour: int = Field(ge=0, le=23, description="First hour of the window.")
    end_hour: int = Field(ge=0, le=23, description="Exclusive end hour (may wrap).")
    presence: float = Field(
        ge=0.0, le=1.0, description="Weighted fraction of class days with activity inside."
    )


class HabitsProfileClassSchema(BaseModel):
    """Rhythm result for one day class."""

    verdict: ProfileVerdict = Field(description="Detector verdict for this class.")
    windows: list[HabitWindowSchema] = Field(
        default_factory=list, description="Claimed windows (empty unless WINDOWS)."
    )
    n_eff: float = Field(ge=0.0, description="Effective observed class days (Kish).")
    required_n_eff: float = Field(
        ge=0.0,
        description="Effective days required before claims — the enforced bound, "
        "published so the user can see exactly where the unlock stands (ADR-184).",
    )
    effective_presence_min: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="The presence a window must REALLY reach for this class — "
        "max(presence_min, Wilson-implied bar at this n_eff). Published because "
        "it is enforced (ADR-184): the configured 0.55 understates the real bar "
        "(≈0.57 weekday / ≈0.70 weekend on a full window, audit C-02).",
    )
    bin_presence: list[float] = Field(
        default_factory=lambda: [0.0] * 24,
        description="Weighted per-hour day-presence (24 values) — the "
        "distribution-level profile, available even when no window is "
        "claimable (heatmap source).",
    )


class HabitsProfileSchema(BaseModel):
    """The stored rhythm profile, or its pre-first-compute shape."""

    computed_at: datetime | None = Field(
        default=None, description="Last nightly recompute; None before the first run."
    )
    weekday: HabitsProfileClassSchema
    weekend: HabitsProfileClassSchema
    active_days_fraction: float = Field(ge=0.0, le=1.0)
    sparse: bool = Field(description="True when usage is too occasional for window claims.")


class HabitResponse(BaseModel):
    """One discrete learned habit row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: HabitKind
    key: str = Field(description="Stable identity within the kind.")
    payload: dict[str, Any] = Field(description="Kind-specific versioned payload.")
    status: HabitStatus
    positive_signals: int = Field(ge=0)
    negative_signals: int = Field(ge=0)
    last_observed_at: datetime
    created_at: datetime


class HabitsCandidateSchema(BaseModel):
    """One recurrence signature under observation (not yet locked).

    The requirement published here IS the enforced existence gate of the
    lock evaluation (ADR-184) — never a front-side re-declaration.
    """

    key: str = Field(description="Domain signature, e.g. 'email+contact'.")
    observed_days: int = Field(ge=0, description="Distinct local days observed in window.")
    required_days: int = Field(ge=1, description="Enforced existence threshold (published).")
    origin: Literal["live", "seed"] = Field(
        default="live",
        description="Provenance: 'live' = typed turns; 'seed' = rebuilt from durable "
        "outcomes by the recompute (stated on the screen, never a different threshold).",
    )


class HabitsStreakSchema(BaseModel):
    """Streak facts from the activity ledger (Lot 1-A4, display only)."""

    current: int = Field(ge=0, description="Consecutive active days ending today or yesterday.")
    longest: int = Field(ge=0, description="Longest run ever recorded in the ledger.")
    milestone_reached: int | None = Field(
        default=None, description="Highest settings-driven milestone at or below current."
    )
    next_milestone: int | None = Field(
        default=None, description="Smallest settings-driven milestone above current."
    )


class HabitsOverviewResponse(BaseModel):
    """Settings-surface payload: preference + profile + habits + candidates."""

    habits_enabled: bool = Field(description="User preference (feature master toggle).")
    profile: HabitsProfileSchema
    streak: HabitsStreakSchema = Field(
        description="Activity streaks + milestone positions (ledger-derived, display only)."
    )
    habits: list[HabitResponse] = Field(default_factory=list)
    candidates: list[HabitsCandidateSchema] = Field(
        default_factory=list,
        description="Recurrence signatures under observation (capped).",
    )
    candidates_more: int = Field(
        default=0,
        ge=0,
        description="Candidates beyond the display cap — a cap is stated, never silent.",
    )


class HabitsSettingsUpdate(BaseModel):
    """User preference update."""

    habits_enabled: bool = Field(description="Enable/disable habit learning.")


class HabitStatusUpdate(BaseModel):
    """Status transition requested by the user."""

    status: Literal["active", "paused", "blocked"] = Field(
        description="Target status; 'blocked' is the never-relearn tombstone."
    )


class HabitExplanationResponse(BaseModel):
    """Why LIA claims this habit — inputs and thresholds, never a score."""

    kind: HabitKind
    key: str
    payload: dict[str, Any]
    positive_signals: int
    negative_signals: int
    status: HabitStatus
    last_observed_at: datetime
    thresholds: dict[str, float | int] = Field(
        description="The exact thresholds the detector applied (published, ADR-184)."
    )
    observed_days: list[str] = Field(
        default_factory=list,
        description="REAL occurrence dates from the ledger (recurring habits "
        "only) — the exact basis of the lock, newest first. The ledger keeps "
        "no message ids on purpose: fabricated references would be false "
        "provenance.",
    )


class HabitsDeleteAllResponse(BaseModel):
    """Result of 'forget everything'."""

    deleted_habits: int = Field(ge=0)
    profile_deleted: bool


class HabitsRecomputeResponse(BaseModel):
    """Result of a manual recompute (same unit of work as the nightly job)."""

    outcome: str = Field(description="computed | skipped_no_delta | skipped_no_activity.")
    profile: HabitsProfileSchema
