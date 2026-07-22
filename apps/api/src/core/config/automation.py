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
    RECURRENCE_LEDGER_MAX_ENTRIES_DEFAULT,
    RECURRENCE_MIN_DISTINCT_DAYS_DEFAULT,
    RECURRENCE_SUGGESTION_COOLDOWN_DAYS_DEFAULT,
    RECURRENCE_WINDOW_DAYS_DEFAULT,
)


class AutomationSettings(BaseSettings):
    """Env-overridable settings for the recurrence→automation suggestion."""

    recurrence_suggestion_enabled: bool = Field(
        default=False,
        description="Enable the recurrence detector + automation suggestion.",
    )
    recurrence_window_days: int = Field(
        default=RECURRENCE_WINDOW_DAYS_DEFAULT,
        ge=3,
        le=60,
        description="Observation window for recurrence detection.",
    )
    recurrence_min_distinct_days: int = Field(
        default=RECURRENCE_MIN_DISTINCT_DAYS_DEFAULT,
        ge=2,
        le=14,
        description="Distinct days with the same request shape required to suggest.",
    )
    recurrence_suggestion_cooldown_days: int = Field(
        default=RECURRENCE_SUGGESTION_COOLDOWN_DAYS_DEFAULT,
        ge=7,
        le=180,
        description="Never re-suggest the same shape within this cooldown.",
    )
    recurrence_ledger_max_entries: int = Field(
        default=RECURRENCE_LEDGER_MAX_ENTRIES_DEFAULT,
        ge=5,
        le=100,
        description="Cap on stored occurrence timestamps per (user, shape).",
    )
