"""Open Loops configuration module (P5, ADR-139).

Commitments-ledger feature flag and nudge-policy thresholds. Every value is
env-overridable (``OPEN_LOOPS_*``) so the nudge cadence can be tuned in
production without a code change.

Defaults are imported from ``src.core.constants`` (NOT from the domain — the
config layer never imports domains, see ``briefing.py``'s rationale).

Phase: interdomain intelligence program, Lot 2
Created: 2026-07-22
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    OPEN_LOOPS_EXPIRY_DAYS_DEFAULT,
    OPEN_LOOPS_EXTRACTION_MAX_ITEMS_DEFAULT,
    OPEN_LOOPS_MAX_OPEN_PER_USER_DEFAULT,
    OPEN_LOOPS_NUDGE_COOLDOWN_DAYS_DEFAULT,
    OPEN_LOOPS_NUDGE_DUE_HOURS_DEFAULT,
    OPEN_LOOPS_NUDGE_STALE_DAYS_DEFAULT,
)


class OpenLoopsSettings(BaseSettings):
    """Env-overridable settings for the open-loops commitments ledger."""

    open_loops_enabled: bool = Field(
        default=True,
        description="Enable the open-loops commitments ledger (extraction + nudging).",
    )
    open_loops_max_open_per_user: int = Field(
        default=OPEN_LOOPS_MAX_OPEN_PER_USER_DEFAULT,
        ge=1,
        le=200,
        description="Hard cap on OPEN loops per user (extraction refuses beyond).",
    )
    open_loops_extraction_max_items: int = Field(
        default=OPEN_LOOPS_EXTRACTION_MAX_ITEMS_DEFAULT,
        ge=1,
        le=20,
        description="Max loops the extractor may open from a single turn.",
    )
    open_loops_nudge_due_hours: int = Field(
        default=OPEN_LOOPS_NUDGE_DUE_HOURS_DEFAULT,
        ge=1,
        le=168,
        description="A loop due within this window (or overdue) is nudge-worthy.",
    )
    open_loops_nudge_stale_days: int = Field(
        default=OPEN_LOOPS_NUDGE_STALE_DAYS_DEFAULT,
        ge=1,
        le=90,
        description="A loop untouched this long is nudge-worthy even without a deadline.",
    )
    open_loops_nudge_cooldown_days: int = Field(
        default=OPEN_LOOPS_NUDGE_COOLDOWN_DAYS_DEFAULT,
        ge=1,
        le=30,
        description="Never surface the same loop twice within this cooldown.",
    )
    open_loops_expiry_days: int = Field(
        default=OPEN_LOOPS_EXPIRY_DAYS_DEFAULT,
        ge=7,
        le=365,
        description="OPEN loops untouched this long are soft-expired (lazy).",
    )
