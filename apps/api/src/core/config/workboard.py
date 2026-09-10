"""Workboard configuration module (ADR-276).

Feature flag and every bound the ticket board enforces. Each value is
env-overridable (``WORKBOARD_*``) so an operator can retune quotas and cadences
without a code change; defaults are imported from ``src.core.constants`` (the
config layer never imports domains — see ``peers.py``'s rationale).

The flag defaults to ``true``, unlike the other program flags: the board is a
core surface of the assistant rather than an optional subsystem, and an
instance that does not want it turns it off explicitly.
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    WORKBOARD_BRIEF_MAX_NOTES_DEFAULT,
    WORKBOARD_CLOSED_HIDE_DAYS_DEFAULT,
    WORKBOARD_COMMENT_MAX_CHARS_DEFAULT,
    WORKBOARD_DESCRIPTION_MAX_CHARS_DEFAULT,
    WORKBOARD_HIDDEN_ROWS_RETENTION_DAYS_DEFAULT,
    WORKBOARD_MAX_CHILDREN_PER_TICKET_DEFAULT,
    WORKBOARD_MAX_RUNS_PER_TICKET_DEFAULT,
    WORKBOARD_MAX_TICKETS_PER_USER_DEFAULT,
    WORKBOARD_NUDGE_COOLDOWN_DAYS_DEFAULT,
    WORKBOARD_NUDGE_DUE_HOURS_DEFAULT,
    WORKBOARD_NUDGE_MAX_ITEMS_DEFAULT,
    WORKBOARD_NUDGE_WAITING_HOURS_DEFAULT,
    WORKBOARD_QUOTA_RETRY_MINUTES_DEFAULT,
    WORKBOARD_RUN_MAX_ATTEMPTS_DEFAULT,
    WORKBOARD_RUN_SWEEP_SECONDS_DEFAULT,
    WORKBOARD_RUN_TIMEOUT_SECONDS_DEFAULT,
    WORKBOARD_TITLE_MAX_CHARS_DEFAULT,
)


class WorkboardSettings(BaseSettings):
    """Env-overridable settings for the ticket board."""

    workboard_enabled: bool = Field(
        default=True,
        description="Enable the workboard (routes, sweep, agent tools, settings section).",
    )
    workboard_run_sweep_seconds: int = Field(
        default=WORKBOARD_RUN_SWEEP_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Interval of the sweep that runs the tickets assigned to LIA.",
    )
    workboard_run_timeout_seconds: int = Field(
        default=WORKBOARD_RUN_TIMEOUT_SECONDS_DEFAULT,
        ge=30,
        le=3600,
        description=(
            "Hard bound of ONE attempt of a ticket run. A run may retry a "
            "transient failure, so the claim it holds is reaped only after the "
            "worst case this and WORKBOARD_RUN_MAX_ATTEMPTS allow."
        ),
    )
    workboard_run_max_attempts: int = Field(
        default=WORKBOARD_RUN_MAX_ATTEMPTS_DEFAULT,
        ge=1,
        le=10,
        description="Transient-failure attempts of ONE run before it settles as failed.",
    )
    workboard_quota_retry_minutes: int = Field(
        default=WORKBOARD_QUOTA_RETRY_MINUTES_DEFAULT,
        ge=1,
        le=1440,
        description="Back-off before a quota-refused ticket is offered to the sweep again.",
    )
    workboard_max_tickets_per_user: int = Field(
        default=WORKBOARD_MAX_TICKETS_PER_USER_DEFAULT,
        ge=1,
        le=100000,
        description="Tickets one account may own, counted exactly at creation.",
    )
    workboard_max_children_per_ticket: int = Field(
        default=WORKBOARD_MAX_CHILDREN_PER_TICKET_DEFAULT,
        ge=1,
        le=1000,
        description="Sub-tickets one ticket may carry (one level — ADR-276 D9).",
    )
    workboard_max_runs_per_ticket: int = Field(
        default=WORKBOARD_MAX_RUNS_PER_TICKET_DEFAULT,
        ge=1,
        le=100,
        description="Runs one ticket may have in its life, « Run now » included (D3b).",
    )
    workboard_hidden_rows_retention_days: int = Field(
        default=WORKBOARD_HIDDEN_ROWS_RETENTION_DAYS_DEFAULT,
        ge=1,
        le=3650,
        description="Days after a ticket closes before its hidden run rows are deleted.",
    )
    workboard_title_max_chars: int = Field(
        default=WORKBOARD_TITLE_MAX_CHARS_DEFAULT,
        ge=20,
        le=1000,
        description="Longest ticket title accepted.",
    )
    workboard_description_max_chars: int = Field(
        default=WORKBOARD_DESCRIPTION_MAX_CHARS_DEFAULT,
        ge=100,
        le=100000,
        description="Longest description accepted — the brief LIA runs.",
    )
    workboard_comment_max_chars: int = Field(
        default=WORKBOARD_COMMENT_MAX_CHARS_DEFAULT,
        ge=50,
        le=50000,
        description="Longest comment accepted.",
    )
    workboard_closed_hide_days_default: int = Field(
        default=WORKBOARD_CLOSED_HIDE_DAYS_DEFAULT,
        ge=0,
        le=3650,
        description="Default of the « hide closed tickets older than » board filter.",
    )
    workboard_nudge_due_hours: int = Field(
        default=WORKBOARD_NUDGE_DUE_HOURS_DEFAULT,
        ge=1,
        le=720,
        description="Heartbeat: a ticket due within this window is nudge-worthy.",
    )
    workboard_nudge_waiting_hours: int = Field(
        default=WORKBOARD_NUDGE_WAITING_HOURS_DEFAULT,
        ge=1,
        le=720,
        description="Heartbeat: a ticket waiting for the person longer than this is nudge-worthy.",
    )
    workboard_nudge_cooldown_days: int = Field(
        default=WORKBOARD_NUDGE_COOLDOWN_DAYS_DEFAULT,
        ge=0,
        le=365,
        description="Heartbeat: days between two nudges about the same ticket.",
    )
    workboard_nudge_max_items: int = Field(
        default=WORKBOARD_NUDGE_MAX_ITEMS_DEFAULT,
        ge=1,
        le=50,
        description="Heartbeat: how many tickets at most reach one decision prompt.",
    )
    workboard_brief_max_notes: int = Field(
        default=WORKBOARD_BRIEF_MAX_NOTES_DEFAULT,
        ge=0,
        le=100,
        description=(
            "How many of the owner's latest notes (their comments since LIA's last "
            "run) a ticket brief carries. Their answer to a confirmation travels "
            "this way; each note is bounded by WORKBOARD_COMMENT_MAX_CHARS."
        ),
    )

    @model_validator(mode="after")
    def timeout_covers_a_sweep_interval(self) -> WorkboardSettings:
        """Refuse a timeout below the sweep interval.

        The reaper releases a claim older than ``workboard_run_timeout_seconds``.
        Below the sweep interval, the next tick would release a run still in
        flight and hand the same ticket to a second worker — the boot-time
        guard the background-runs settings use for the same class of mistake.

        Returns:
            The validated settings.

        Raises:
            ValueError: When the timeout is shorter than one sweep interval.
        """
        if self.workboard_run_timeout_seconds < self.workboard_run_sweep_seconds:
            raise ValueError(
                "WORKBOARD_RUN_TIMEOUT_SECONDS must be >= WORKBOARD_RUN_SWEEP_SECONDS: "
                "a shorter timeout reaps runs that are still in flight"
            )
        return self
