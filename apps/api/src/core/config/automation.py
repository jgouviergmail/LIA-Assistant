"""Automation configuration module (P12, ADR-140; recurring needs ADR-375).

The request ledger's storage bounds and the recurring-need bars. Every value
is env-overridable (``RECURRENCE_*``). Defaults imported from
``src.core.constants`` (config never imports domains).

Phase: interdomain intelligence program, Lot 3
Created: 2026-07-22
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    RECURRENCE_AUTOMATE_MIN_DAYS_DEFAULT,
    RECURRENCE_AUTOMATE_SHARE_DEFAULT,
    RECURRENCE_DAY_HOURS_CAP_DEFAULT,
    RECURRENCE_LEDGER_MAX_ENTRIES_DEFAULT,
    RECURRENCE_MIN_DISTINCT_DAYS_DEFAULT,
    RECURRENCE_NEED_MIN_WEEKS_DEFAULT,
    RECURRENCE_NEED_RECENT_DAYS_DEFAULT,
    RECURRENCE_PART_OF_DAY_SHARE_DEFAULT,
    RECURRENCE_WEEKEND_TOLERANCE_DEFAULT,
    RECURRENCE_WEEKLY_DOW_FRACTION_DEFAULT,
    RECURRENCE_WEEKLY_MIN_SAME_DOW_DEFAULT,
    RECURRENCE_WINDOW_DAYS_DEFAULT,
)


class AutomationSettings(BaseSettings):
    """Env-overridable settings for the request ledger and the recurring needs.

    ADR-375: a need is a domain asked on enough distinct days — the hour is a
    descriptor, never a condition (the ADR-214 shape LOCKS are retired).
    Calibrated by ``scripts/habits/measure_proposals.py``.
    """

    recurrence_suggestion_enabled: bool = Field(
        default=True,
        description="Let LIA show a habit proposal under a chat answer (ADR-375). Learning, "
        "the proposals inbox and the nightly sync do not depend on it.",
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
        description="Distinct days a domain must be asked on for a recurring need to EXIST.",
    )
    recurrence_need_min_weeks: int = Field(
        default=RECURRENCE_NEED_MIN_WEEKS_DEFAULT,
        ge=1,
        le=8,
        description="Distinct ISO weeks a recurring need's days must span (ADR-375).",
    )
    recurrence_need_recent_days: int = Field(
        default=RECURRENCE_NEED_RECENT_DAYS_DEFAULT,
        ge=1,
        le=60,
        description="A recurring need lapses when its latest ask is older than this.",
    )
    recurrence_automate_share: float = Field(
        default=RECURRENCE_AUTOMATE_SHARE_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Share of the person's active days a need must cover before LIA "
        "proposes automating it (weekly needs are judged on their weekday instead).",
    )
    recurrence_automate_min_days: int = Field(
        default=RECURRENCE_AUTOMATE_MIN_DAYS_DEFAULT,
        ge=2,
        le=60,
        description="Need days required, with the share, before proposing an automation.",
    )
    recurrence_part_of_day_share: float = Field(
        default=RECURRENCE_PART_OF_DAY_SHARE_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Share of asks that must fall in one part of the day to name it.",
    )
    recurrence_ledger_max_entries: int = Field(
        default=RECURRENCE_LEDGER_MAX_ENTRIES_DEFAULT,
        ge=7,
        le=100,
        description="Cap on stored DAY entries per (user, domain) — v2 stores days, "
        "not raw occurrences.",
    )
    recurrence_day_hours_cap: int = Field(
        default=RECURRENCE_DAY_HOURS_CAP_DEFAULT,
        ge=1,
        le=24,
        description="Cap on stored DISTINCT clock hours per day entry (one per hour, ADR-375).",
    )
    recurrence_weekend_tolerance: int = Field(
        default=RECURRENCE_WEEKEND_TOLERANCE_DEFAULT,
        ge=0,
        le=4,
        description="Weekend days tolerated before a need's cadence stops being 'weekdays'.",
    )
    recurrence_weekly_min_same_dow: int = Field(
        default=RECURRENCE_WEEKLY_MIN_SAME_DOW_DEFAULT,
        ge=3,
        le=10,
        description="Distinct same-weekday days required for a weekly cadence.",
    )
    recurrence_weekly_dow_fraction: float = Field(
        default=RECURRENCE_WEEKLY_DOW_FRACTION_DEFAULT,
        ge=0.5,
        le=1.0,
        description="Fraction of a need's days on its modal weekday for a weekly cadence.",
    )

    @model_validator(mode="after")
    def _ledger_cap_covers_the_window(self) -> AutomationSettings:
        """Refuse a day-entry cap below the observation window.

        The ledger stores one entry per day and trims to the cap; the needs
        read the window. A cap below the window silently shortens EVERY
        window — a weekly need needs its fifth slot, and the v1 occurrence
        cap starved the detector exactly this way (ADR-214). Loud, like the
        sibling settings validators: learning on a truncated ledger is the
        silent failure this subsystem has already paid for once.
        """
        if self.recurrence_ledger_max_entries < self.recurrence_window_days:
            raise ValueError(
                "RECURRENCE_LEDGER_MAX_ENTRIES must be >= RECURRENCE_WINDOW_DAYS "
                f"(got entries={self.recurrence_ledger_max_entries}, "
                f"window={self.recurrence_window_days})"
            )
        return self

    @model_validator(mode="after")
    def _need_bars_fit_the_window(self) -> AutomationSettings:
        """Refuse need bars no window could ever satisfy (ADR-375).

        A recency or automation bar wider than the window, or an existence bar
        above the automation one, silently turns a learning rule off: loud at
        boot, like the ledger cap above.
        """
        window = self.recurrence_window_days
        if (
            self.recurrence_need_recent_days > window
            or self.recurrence_automate_min_days > window
            or self.recurrence_min_distinct_days > self.recurrence_automate_min_days
        ):
            raise ValueError(
                "Need bars must fit the window: RECURRENCE_NEED_RECENT_DAYS and "
                "RECURRENCE_AUTOMATE_MIN_DAYS <= RECURRENCE_WINDOW_DAYS, and "
                "RECURRENCE_MIN_DISTINCT_DAYS <= RECURRENCE_AUTOMATE_MIN_DAYS "
                f"(got recent={self.recurrence_need_recent_days}, "
                f"automate_min={self.recurrence_automate_min_days}, "
                f"min={self.recurrence_min_distinct_days}, window={window})"
            )
        return self
