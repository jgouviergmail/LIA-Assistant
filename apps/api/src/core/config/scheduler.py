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

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS,
    SCHEDULED_ACTIONS_MAX_CONCURRENCY,
    SCHEDULED_ACTIONS_STALE_TIMEOUT_MINUTES,
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
            "Beyond this, the action is forcibly cancelled and surfaced as "
            "TIMEOUT in the action_runs audit table. "
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
