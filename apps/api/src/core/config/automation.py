"""Automation configuration module (P12, ADR-140).

Recurrence-detection thresholds for the automation suggestion. Every value
is env-overridable (``RECURRENCE_*``). Defaults imported from
``src.core.constants`` (config never imports domains).

Phase: interdomain intelligence program, Lot 3
Created: 2026-07-22
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    RECURRENCE_DAY_HOURS_CAP_DEFAULT,
    RECURRENCE_LEDGER_MAX_ENTRIES_DEFAULT,
    RECURRENCE_LOCK_HALF_AGREE_HOURS_DEFAULT,
    RECURRENCE_LOCK_HALF_R_MIN_DEFAULT,
    RECURRENCE_LOCK_MIN_OCCURRENCES_DEFAULT,
    RECURRENCE_LOCK_MIN_SPREAD_DAYS_DEFAULT,
    RECURRENCE_LOCK_R_MIN_DEFAULT,
    RECURRENCE_MIN_DISTINCT_DAYS_DEFAULT,
    RECURRENCE_SHAPE_MIN_DAYS_DEFAULT,
    RECURRENCE_SUGGESTION_COOLDOWN_DAYS_DEFAULT,
    RECURRENCE_WEEKEND_TOLERANCE_DEFAULT,
    RECURRENCE_WEEKLY_DOW_FRACTION_DEFAULT,
    RECURRENCE_WEEKLY_MIN_SAME_DOW_DEFAULT,
    RECURRENCE_WINDOW_DAYS_DEFAULT,
)


class AutomationSettings(BaseSettings):
    """Env-overridable settings for the recurrence→automation suggestion.

    v2 (ADR-214): per-day ledger storage and shape LOCKS. A user-facing
    suggestion only fires when a lock holds — thresholds calibrated by the
    habits-plan simulation harness (§4.2: 0% false suggestions on
    spread/sporadic usage, 90.7% weekly detection vs 0% before).
    """

    recurrence_suggestion_enabled: bool = Field(
        default=True,
        description="Enable the recurrence detector + automation suggestion.",
    )
    recurrence_window_days: int = Field(
        default=RECURRENCE_WINDOW_DAYS_DEFAULT,
        ge=7,
        le=60,
        description="Observation window for recurrence detection.",
    )
    recurrence_min_distinct_days: int = Field(
        default=RECURRENCE_MIN_DISTINCT_DAYS_DEFAULT,
        ge=2,
        le=14,
        description="Distinct days with the same request shape for the habit to EXIST "
        "(internal — a suggestion additionally requires a lock).",
    )
    recurrence_suggestion_cooldown_days: int = Field(
        default=RECURRENCE_SUGGESTION_COOLDOWN_DAYS_DEFAULT,
        ge=7,
        le=180,
        description="Never re-suggest the same shape within this cooldown.",
    )
    recurrence_ledger_max_entries: int = Field(
        default=RECURRENCE_LEDGER_MAX_ENTRIES_DEFAULT,
        ge=7,
        le=100,
        description="Cap on stored DAY entries per (user, shape) — v2 stores days, "
        "not raw occurrences (the occurrence cap starved the spread lock).",
    )
    recurrence_day_hours_cap: int = Field(
        default=RECURRENCE_DAY_HOURS_CAP_DEFAULT,
        ge=1,
        le=24,
        description="Cap on stored occurrence hours per day entry.",
    )
    recurrence_lock_min_occurrences: int = Field(
        default=RECURRENCE_LOCK_MIN_OCCURRENCES_DEFAULT,
        ge=4,
        le=50,
        description="Occurrences required before a time-lock may be claimed.",
    )
    recurrence_lock_min_spread_days: int = Field(
        default=RECURRENCE_LOCK_MIN_SPREAD_DAYS_DEFAULT,
        ge=5,
        le=60,
        description="First-to-last day spread required for a time-lock.",
    )
    recurrence_lock_r_min: float = Field(
        default=RECURRENCE_LOCK_R_MIN_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Circular concentration (R) required for a time-lock.",
    )
    recurrence_lock_half_r_min: float = Field(
        default=RECURRENCE_LOCK_HALF_R_MIN_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Split-half consistency: R required on each half.",
    )
    recurrence_lock_half_agree_hours: float = Field(
        default=RECURRENCE_LOCK_HALF_AGREE_HOURS_DEFAULT,
        ge=0.5,
        le=12.0,
        description="Split-half consistency: max circular distance between half means.",
    )
    recurrence_shape_min_days: int = Field(
        default=RECURRENCE_SHAPE_MIN_DAYS_DEFAULT,
        ge=7,
        le=60,
        description="Distinct days before the daily/workdays shape is labeled "
        "(too early mislabels a daily habit as workdays — measured).",
    )
    recurrence_weekend_tolerance: int = Field(
        default=RECURRENCE_WEEKEND_TOLERANCE_DEFAULT,
        ge=0,
        le=4,
        description="Weekend days tolerated in a 'workdays' labeling.",
    )
    recurrence_weekly_min_same_dow: int = Field(
        default=RECURRENCE_WEEKLY_MIN_SAME_DOW_DEFAULT,
        ge=3,
        le=10,
        description="Distinct same-weekday days required for a weekly lock.",
    )
    recurrence_weekly_dow_fraction: float = Field(
        default=RECURRENCE_WEEKLY_DOW_FRACTION_DEFAULT,
        ge=0.5,
        le=1.0,
        description="Fraction of distinct days on the modal weekday for a weekly lock.",
    )
