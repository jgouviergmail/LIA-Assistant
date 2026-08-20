"""Habits configuration module (ADR-214).

Learned user rhythm + recurring-request habits. Every value is
env-overridable (``HABITS_*``). Defaults imported from
``src.core.constants`` (config never imports domains).

The rhythm-detector thresholds were calibrated by the simulation harness of
the habits program plan (300 trials/scenario — see
``docs/plans/2026-08-05-habitudes-utilisateur-programme.md`` §4.1);
recalibrating them requires replaying that harness, not guessing.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    HABITS_ABSENCE_GAP_FACTOR_DEFAULT,
    HABITS_ABSENCE_MIN_DAYS_DEFAULT,
    HABITS_CANDIDATES_DISPLAY_MAX_DEFAULT,
    HABITS_CAPTURE_MIN_DEFAULT,
    HABITS_DEVIATION_GRACE_HOURS_DEFAULT,
    HABITS_DEVIATION_OFFER_COOLDOWN_DAYS_DEFAULT,
    HABITS_DEVIATION_STOP_AFTER_IGNORED_DEFAULT,
    HABITS_EXIT_CAPTURE_DEFAULT,
    HABITS_EXIT_PRESENCE_DEFAULT,
    HABITS_EXIT_SELECTIVITY_DEFAULT,
    HABITS_HALF_LIFE_DAYS_DEFAULT,
    HABITS_HALF_PRESENCE_MIN_DEFAULT,
    HABITS_MAX_CLAIMED_HOURS_DEFAULT,
    HABITS_MAX_HABITS_PER_KIND_DEFAULT,
    HABITS_MIN_NEFF_WEEKDAY_DEFAULT,
    HABITS_MIN_NEFF_WEEKEND_DEFAULT,
    HABITS_PRESENCE_MIN_DEFAULT,
    HABITS_PROFILE_JOB_HOUR_UTC_DEFAULT,
    HABITS_RECENT_DAYS_DEFAULT,
    HABITS_RECENT_MIN_DEFAULT,
    HABITS_SELECTIVITY_MIN_DEFAULT,
    HABITS_SPARSE_ACTIVE_DAYS_MIN_DEFAULT,
    HABITS_STREAK_MILESTONES_DEFAULT,
    HABITS_WAKING_HOURS_DEFAULT,
    HABITS_WILSON_FLOOR_DEFAULT,
    HABITS_WINDOW_DAYS_DEFAULT,
)


class HabitsSettings(BaseSettings):
    """Env-overridable settings for the learned-habits subsystem."""

    habits_enabled: bool = Field(
        default=True,
        description="Master flag for the habits subsystem (profile job, API, consumption).",
    )
    habits_tick_scoring_enabled: bool = Field(
        default=True,
        description="Deterministic proactive-tick scoring: defer heartbeat "
        "ticks toward learned rhythm windows (never widening the user's "
        "bounds, anti-starvation guaranteed). Requires habits_enabled.",
    )
    habits_window_days: int = Field(
        default=HABITS_WINDOW_DAYS_DEFAULT,
        ge=14,
        le=112,
        description="Sliding observation window for the rhythm profile.",
    )
    habits_half_life_days: float = Field(
        default=HABITS_HALF_LIFE_DAYS_DEFAULT,
        ge=3.0,
        le=56.0,
        description="Exponential day-weight half-life (unlearning speed).",
    )
    habits_presence_min: float = Field(
        default=HABITS_PRESENCE_MIN_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Entry threshold: weighted day-presence a window must reach.",
    )
    habits_wilson_floor: float = Field(
        default=HABITS_WILSON_FLOOR_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Entry threshold: Wilson 99% lower bound on window presence.",
    )
    habits_half_presence_min: float = Field(
        default=HABITS_HALF_PRESENCE_MIN_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Split-half consistency: presence required on each half of days.",
    )
    habits_capture_min: float = Field(
        default=HABITS_CAPTURE_MIN_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Selectivity gate: fraction of activity the claimed union must capture.",
    )
    habits_selectivity_min: float = Field(
        default=HABITS_SELECTIVITY_MIN_DEFAULT,
        ge=1.0,
        le=5.0,
        description="Selectivity gate: capture over waking-day share ratio.",
    )
    habits_exit_presence: float = Field(
        default=HABITS_EXIT_PRESENCE_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Hysteresis exit: presence below which a claimed window is dropped.",
    )
    habits_exit_capture: float = Field(
        default=HABITS_EXIT_CAPTURE_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Hysteresis exit: capture below which claims are dropped.",
    )
    habits_exit_selectivity: float = Field(
        default=HABITS_EXIT_SELECTIVITY_DEFAULT,
        ge=1.0,
        le=5.0,
        description="Hysteresis exit: selectivity below which claims are dropped.",
    )
    habits_min_neff_weekday: float = Field(
        default=HABITS_MIN_NEFF_WEEKDAY_DEFAULT,
        ge=1.0,
        description="Kish effective weekday-days required before any claim.",
    )
    habits_min_neff_weekend: float = Field(
        default=HABITS_MIN_NEFF_WEEKEND_DEFAULT,
        ge=1.0,
        description="Kish effective weekend-days required before any claim.",
    )
    habits_recent_days: int = Field(
        default=HABITS_RECENT_DAYS_DEFAULT,
        ge=3,
        le=56,
        description="Trailing raw-presence window a claim must stay alive in.",
    )
    habits_recent_min: float = Field(
        default=HABITS_RECENT_MIN_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Minimum raw presence over the trailing window.",
    )
    habits_max_claimed_hours: int = Field(
        default=HABITS_MAX_CLAIMED_HOURS_DEFAULT,
        ge=2,
        le=12,
        description="Cap on total claimed window hours per day class.",
    )
    habits_waking_hours: float = Field(
        default=HABITS_WAKING_HOURS_DEFAULT,
        ge=8.0,
        le=24.0,
        description="Normative waking-day length used as the selectivity reference.",
    )
    habits_sparse_active_days_min: float = Field(
        default=HABITS_SPARSE_ACTIVE_DAYS_MIN_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Below this weighted active-day fraction the profile is `sparse`.",
    )
    habits_max_habits_per_kind: int = Field(
        default=HABITS_MAX_HABITS_PER_KIND_DEFAULT,
        ge=1,
        le=32,
        description="Cap on stored habits per (user, kind).",
    )
    habits_candidates_display_max: int = Field(
        default=HABITS_CANDIDATES_DISPLAY_MAX_DEFAULT,
        ge=1,
        le=20,
        description="Recurrence candidates shown 'under observation' in the "
        "settings panel; the remainder is counted, never silently dropped.",
    )
    habits_streak_milestones: list[int] = Field(
        default_factory=lambda: list(HABITS_STREAK_MILESTONES_DEFAULT),
        description="Streak milestone lengths (days) celebrated in the UI. "
        "DISPLAY thresholds only — detection calibration (ADR-214) is a "
        "separate authority. Env format: JSON list, e.g. [7,30,100].",
    )
    habits_profile_job_hour_utc: int = Field(
        default=HABITS_PROFILE_JOB_HOUR_UTC_DEFAULT,
        ge=0,
        le=23,
        description="UTC hour of the nightly profile recompute job.",
    )
    habits_deviation_offer_cooldown_days: int = Field(
        default=HABITS_DEVIATION_OFFER_COOLDOWN_DAYS_DEFAULT,
        ge=1,
        le=60,
        description="Per-habit cooldown between missed-routine offers.",
    )
    habits_deviation_stop_after_ignored: int = Field(
        default=HABITS_DEVIATION_STOP_AFTER_IGNORED_DEFAULT,
        ge=1,
        le=10,
        description="Consecutive ignored offers before the habit's offers go mute "
        "(the stop rule that bounds nagging on an abandoned routine).",
    )
    habits_deviation_grace_hours: float = Field(
        default=HABITS_DEVIATION_GRACE_HOURS_DEFAULT,
        ge=0.0,
        le=12.0,
        description="Hours past the learned trigger before a slot counts as missed.",
    )
    habits_absence_gap_factor: float = Field(
        default=HABITS_ABSENCE_GAP_FACTOR_DEFAULT,
        ge=1.0,
        le=20.0,
        description="A gap counts as an unusual absence at factor × the user's "
        "own typical gap (relative — never an absolute threshold).",
    )
    habits_absence_min_days: int = Field(
        default=HABITS_ABSENCE_MIN_DAYS_DEFAULT,
        ge=1,
        le=60,
        description="Floor below which a gap is never an 'absence'.",
    )
