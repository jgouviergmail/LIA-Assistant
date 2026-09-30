"""
Scheduler configuration module.

Contains settings for background scheduling (APScheduler) — currently focused
on the scheduled-actions executor lifecycle (per-action wall-clock timeout
and stale-recovery threshold).

Phase: v1.21 — Timeout centralization (Vague 2)
Created: 2026-05-15
Reference: docs/technical/TIMEOUT_REGISTRY.md
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    REMINDER_PROCESSING_STALE_TIMEOUT_MINUTES_DEFAULT,
    SCHEDULED_ACTIONS_CONDITION_CHECK_MINUTES_DEFAULT,
    SCHEDULED_ACTIONS_CONDITION_MAX_FIRES_PER_DAY_DEFAULT,
    SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS,
    SCHEDULED_ACTIONS_MAX_CONCURRENCY,
    SCHEDULED_ACTIONS_RUNS_RETENTION_DAYS,
    SCHEDULED_ACTIONS_STALE_TIMEOUT_MINUTES,
    SCHEDULED_ACTIONS_WEATHER_CHECK_MINUTES_DEFAULT,
    SCHEDULED_ACTIONS_WEATHER_HORIZON_HOURS_DEFAULT,
    SCHEDULED_ACTIONS_WEATHER_HORIZON_HOURS_MAX,
    SCHEDULED_ACTIONS_WEATHER_MIN_PRECIPITATION_PERCENT_DEFAULT,
)


class SchedulerSettings(BaseSettings):
    """Settings for background scheduling (APScheduler-driven jobs)."""

    # ========================================================================
    # Scheduled Actions Executor
    # ========================================================================

    scheduled_actions_execution_timeout_seconds: int = Field(
        default=SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS,
        ge=30,
        le=1800,
        description=(
            "Per-action wall-clock timeout for the scheduled-actions executor. "
            "Beyond this, the action is forcibly cancelled and recorded as a "
            "FAILURE in scheduled_action_runs (ADR-265). "
            "Symptom if too low: legitimate actions (long LLM-bound prompts) "
            "fail with TIMEOUT. Symptom if too high: a stuck action keeps a "
            "worker slot busy, delaying subsequent triggers."
        ),
    )

    scheduled_actions_max_concurrency: int = Field(
        default=SCHEDULED_ACTIONS_MAX_CONCURRENCY,
        ge=1,
        le=20,
        description=(
            "How many actions of one batch the executor may run at the same "
            "time. Each action is an LLM call and opens its OWN database "
            "session, so concurrency is safe here. "
            "Symptom if too low: a long batch serialises past the 60s tick and "
            "APScheduler drops the following ticks (max_instances=1), delaying "
            "actions that were due. Symptom if too high: a batch bursts against "
            "the LLM provider and the connection pool. Set to 1 to restore the "
            "strictly sequential behaviour."
        ),
    )

    scheduled_actions_runs_retention_days: int = Field(
        default=SCHEDULED_ACTIONS_RUNS_RETENTION_DAYS,
        ge=7,
        le=3650,
        description=(
            "How many days of routine run history (scheduled_action_runs) are "
            "kept. The weekly timeline reads the current week only; older rows "
            "are purged at every executor tick. Symptom if too low: the export "
            "of a user's own execution history is short. Symptom if too high: "
            "the table grows with every routine of every account."
        ),
    )

    # ------------------------------------------------------------------------
    # Condition routines (ADR-322): the system's clock, not the person's
    # ------------------------------------------------------------------------

    scheduled_actions_condition_check_minutes: int = Field(
        default=SCHEDULED_ACTIONS_CONDITION_CHECK_MINUTES_DEFAULT,
        ge=5,
        le=1440,
        description=(
            "How often a condition routine reading the person's mail, tasks, "
            "calendar or documents is checked, day and night. Each routine is "
            "phase-shifted by its own id so checks never align. Never shorter "
            "than the cache its source reads through, when it has one (the "
            "mail search: the effective interval is the larger of the two). "
            "Symptom if too low: more provider calls and more consultation "
            "rows for no fresher answer. Symptom if too high: a watched fact "
            "is announced later."
        ),
    )

    scheduled_actions_weather_check_minutes: int = Field(
        default=SCHEDULED_ACTIONS_WEATHER_CHECK_MINUTES_DEFAULT,
        ge=10,
        le=1440,
        description=(
            "How often a weather-change routine is checked. It reads Google "
            "Weather's hourly forecast, and every check is two billed calls on "
            "the deployment's key, attributed to the routine's owner. Never "
            "longer than SCHEDULED_ACTIONS_WEATHER_HORIZON_HOURS (refused at "
            "boot): the hours between two checks' windows would be read by nobody."
        ),
    )

    scheduled_actions_weather_horizon_hours: int = Field(
        default=SCHEDULED_ACTIONS_WEATHER_HORIZON_HOURS_DEFAULT,
        ge=1,
        le=SCHEDULED_ACTIONS_WEATHER_HORIZON_HOURS_MAX,
        description=(
            "How far ahead a weather-change routine looks for rain, drizzle, "
            "snow or a thunderstorm, in hours. The hour under way counts. "
            "Symptom if too high: a change announced hours before it matters, "
            "and forecasts that move before it comes. Symptom if too low: the "
            "announcement arrives too late to act on."
        ),
    )

    scheduled_actions_weather_min_precipitation_percent: int = Field(
        default=SCHEDULED_ACTIONS_WEATHER_MIN_PRECIPITATION_PERCENT_DEFAULT,
        ge=0,
        le=99,
        description=(
            "A forecast hour triggers a weather-change routine only when its "
            "precipitation probability is STRICTLY above this percentage; an "
            "hour the provider gives no probability for never does. Symptom if "
            "too low: a routine fires on a mere chance of showers. Symptom if "
            "too high: only near-certain changes are announced."
        ),
    )

    scheduled_actions_condition_max_fires_per_day: int = Field(
        default=SCHEDULED_ACTIONS_CONDITION_MAX_FIRES_PER_DAY_DEFAULT,
        ge=1,
        le=96,
        description=(
            "Most runs one condition routine may start in one local day. A new "
            "fact past the cap is not dropped: it stays new and runs on the "
            "next day's first check if it still holds. Symptom if too low: a "
            "busy watch falls silent until midnight. Symptom if too high: a "
            "flapping source becomes a stream of pipelines and notifications."
        ),
    )

    reminder_processing_stale_timeout_minutes: int = Field(
        default=REMINDER_PROCESSING_STALE_TIMEOUT_MINUTES_DEFAULT,
        ge=1,
        le=120,
        description=(
            "Recovery threshold for reminder claims (ADR-304). A reminder is "
            "claimed (PROCESSING, committed) before it is notified; one still "
            "PROCESSING past this duration was abandoned by a crash and is "
            "released to PENDING at the next tick. MUST exceed the time one "
            "notification can take (message generation + push), or a live "
            "claim is released under its worker and the reminder sent twice."
        ),
    )

    scheduled_actions_stale_timeout_minutes: int = Field(
        default=SCHEDULED_ACTIONS_STALE_TIMEOUT_MINUTES,
        ge=1,
        le=120,
        description=(
            "Recovery threshold for stale scheduled actions. An action stuck "
            "in 'executing' state past this duration is reset to 'active' by "
            "recover_stale_executing(), called at every scheduler tick. "
            "MUST be greater than scheduled_actions_execution_timeout_seconds "
            "to avoid recovering still-running actions."
        ),
    )

    @model_validator(mode="after")
    def _weather_checks_leave_no_hour_unread(self) -> SchedulerSettings:
        """Refuse weather checks further apart than the horizon they read.

        A check at T reads the changes due up to T + horizon; the next one, at
        T + interval, starts there only if the interval is not longer. Past
        it, a shower in between is announced by no check at all.
        """
        horizon_minutes = self.scheduled_actions_weather_horizon_hours * 60
        if self.scheduled_actions_weather_check_minutes > horizon_minutes:
            raise ValueError(
                "SCHEDULED_ACTIONS_WEATHER_CHECK_MINUTES must be <= "
                "SCHEDULED_ACTIONS_WEATHER_HORIZON_HOURS * 60 (got check="
                f"{self.scheduled_actions_weather_check_minutes}, "
                f"horizon={self.scheduled_actions_weather_horizon_hours} h)"
            )
        return self
