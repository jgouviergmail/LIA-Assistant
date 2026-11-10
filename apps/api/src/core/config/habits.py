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
    HABITS_EXIT_CAPTURE_DEFAULT,
    HABITS_EXIT_PRESENCE_DEFAULT,
    HABITS_EXIT_SELECTIVITY_DEFAULT,
    HABITS_HALF_LIFE_DAYS_DEFAULT,
    HABITS_HALF_PRESENCE_MIN_DEFAULT,
    HABITS_MAX_CLAIMED_HOURS_DEFAULT,
    HABITS_MAX_HABITS_PER_KIND_DEFAULT,
    HABITS_MIN_NEFF_WEEKDAY_DEFAULT,
    HABITS_MIN_NEFF_WEEKEND_DEFAULT,
    HABITS_PRESENCE_CLIENT_THROTTLE_MINUTES_DEFAULT,
    HABITS_PRESENCE_LAST_TTL_DAYS_DEFAULT,
    HABITS_PRESENCE_MIN_DEFAULT,
    HABITS_PROFILE_JOB_HOUR_UTC_DEFAULT,
    HABITS_PROPOSAL_CHAT_GAP_HOURS_DEFAULT,
    HABITS_PROPOSAL_CHAT_REPEAT_DAYS_DEFAULT,
    HABITS_PROPOSAL_CONNECTOR_MIN_DAYS_DEFAULT,
    HABITS_PROPOSAL_FAILURE_STREAK_DEFAULT,
    HABITS_PROPOSAL_MANUAL_MIN_DAYS_DEFAULT,
    HABITS_PROPOSAL_MANUAL_MIN_RUNS_DEFAULT,
    HABITS_PROPOSAL_MUTE_AFTER_REFUSALS_DEFAULT,
    HABITS_PROPOSAL_RESURFACE_DAYS_DEFAULT,
    HABITS_PROPOSAL_ROUTINE_GAP_HOURS_DEFAULT,
    HABITS_PROPOSAL_SILENT_MIN_NOTIFICATIONS_DEFAULT,
    HABITS_PROPOSAL_SNOOZE_DAYS_DEFAULT,
    HABITS_PROPOSAL_WINDOW_MAX_EXTENSION_HOURS_DEFAULT,
    HABITS_PROPOSAL_WINDOW_MIN_CELLS_DEFAULT,
    HABITS_PROPOSAL_WINDOW_MIN_DAYS_DEFAULT,
    HABITS_PROPOSAL_WINDOW_MIN_SHARE_DEFAULT,
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
    habits_proposal_routine_gap_hours: float = Field(
        default=HABITS_PROPOSAL_ROUTINE_GAP_HOURS_DEFAULT,
        ge=0.5,
        le=12.0,
        description="A need asked this far from every time of a routine reading it is not "
        "served by it; a routine launched by hand this far from its time is proposed moved.",
    )
    habits_proposal_manual_min_runs: int = Field(
        default=HABITS_PROPOSAL_MANUAL_MIN_RUNS_DEFAULT,
        ge=2,
        le=30,
        description="Manual launches of a routine before LIA proposes moving it.",
    )
    habits_proposal_manual_min_days: int = Field(
        default=HABITS_PROPOSAL_MANUAL_MIN_DAYS_DEFAULT,
        ge=2,
        le=30,
        description="Distinct days those manual launches must span.",
    )
    habits_proposal_failure_streak: int = Field(
        default=HABITS_PROPOSAL_FAILURE_STREAK_DEFAULT,
        ge=1,
        le=20,
        description="Consecutive failures of a routine before LIA proposes a look at it.",
    )
    habits_proposal_window_min_days: int = Field(
        default=HABITS_PROPOSAL_WINDOW_MIN_DAYS_DEFAULT,
        ge=1,
        le=60,
        description="Days present outside the notification hours before proposing to widen "
        "them; an hour joins the extension only when present on this many days.",
    )
    habits_proposal_window_min_cells: int = Field(
        default=HABITS_PROPOSAL_WINDOW_MIN_CELLS_DEFAULT,
        ge=1,
        le=1000,
        description="Present hours outside the notification hours, over the window.",
    )
    habits_proposal_window_min_share: float = Field(
        default=HABITS_PROPOSAL_WINDOW_MIN_SHARE_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Share of present hours that must fall outside the notification hours.",
    )
    habits_proposal_window_max_extension_hours: int = Field(
        default=HABITS_PROPOSAL_WINDOW_MAX_EXTENSION_HOURS_DEFAULT,
        ge=1,
        le=8,
        description="Most hours added on each side of the notification hours (contiguous).",
    )
    habits_proposal_silent_min_notifications: int = Field(
        default=HABITS_PROPOSAL_SILENT_MIN_NOTIFICATIONS_DEFAULT,
        ge=5,
        le=1000,
        description="Proactive notifications sent with no reaction before LIA asks whether "
        "they are worth keeping.",
    )
    habits_proposal_connector_min_days: int = Field(
        default=HABITS_PROPOSAL_CONNECTOR_MIN_DAYS_DEFAULT,
        ge=1,
        le=60,
        description="Days a domain was asked with no connector of its category before "
        "proposing to connect one.",
    )
    habits_proposal_mute_after_refusals: int = Field(
        default=HABITS_PROPOSAL_MUTE_AFTER_REFUSALS_DEFAULT,
        ge=1,
        le=20,
        description="Refusals of one kind of proposal that silence that kind for the person.",
    )
    habits_proposal_snooze_days: int = Field(
        default=HABITS_PROPOSAL_SNOOZE_DAYS_DEFAULT,
        ge=1,
        le=180,
        description="A proposal put off with « later » reopens after this many days, if "
        "still true.",
    )
    habits_proposal_resurface_days: int = Field(
        default=HABITS_PROPOSAL_RESURFACE_DAYS_DEFAULT,
        ge=7,
        le=365,
        description="An accepted proposal may come back after this many days, if true again.",
    )
    habits_proposal_chat_gap_hours: int = Field(
        default=HABITS_PROPOSAL_CHAT_GAP_HOURS_DEFAULT,
        ge=1,
        le=168,
        description="At most one proposal is shown under a chat answer per this many hours.",
    )
    habits_proposal_chat_repeat_days: int = Field(
        default=HABITS_PROPOSAL_CHAT_REPEAT_DAYS_DEFAULT,
        ge=1,
        le=90,
        description="A proposal already shown under a chat answer may be shown there again "
        "after this many days, while it stays open.",
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
    habits_presence_enabled: bool = Field(
        default=True,
        description="Bank an activity hour when the user OPENS the app (visibility "
        "ping). Thumbs on notifications always count; a sent notification never does. "
        "Requires habits_enabled. ON by default since 2026-09-11 (Q5): a person who "
        "reads without typing is present, and a rhythm learned from typed turns "
        "alone silenced two accounts that only read.",
    )
    habits_presence_client_throttle_minutes: int = Field(
        default=HABITS_PRESENCE_CLIENT_THROTTLE_MINUTES_DEFAULT,
        ge=1,
        le=120,
        description="Minimum minutes between two presence pings from one client "
        "(published to the frontend; the server banks at most one hour per local hour).",
    )
    habits_presence_last_ttl_days: int = Field(
        default=HABITS_PRESENCE_LAST_TTL_DAYS_DEFAULT,
        ge=1,
        le=365,
        description="Sliding TTL of the last-presence marker the heartbeat inactivity "
        "gate reads.",
    )
