"""
Locks configuration module.

Contains the bounds of the locks the application waits on. Today: the OAuth
refresh door's bounded wait for a row (audit AC-029) — the per-(user,
connector) Redis lock it replaced guarded one refresh path of four.

Phase: v1.21 — Timeout centralization (Vague 2)
Created: 2026-05-15
Reference: docs/technical/TIMEOUT_REGISTRY.md
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import OAUTH_REFRESH_WRITE_LOCK_TIMEOUT_MS_DEFAULT


class LocksSettings(BaseSettings):
    """Settings for the locks the application waits on."""

    # ========================================================================
    # OAuth refresh door (audit AC-029)
    # ========================================================================

    oauth_refresh_write_lock_timeout_ms: int = Field(
        default=OAUTH_REFRESH_WRITE_LOCK_TIMEOUT_MS_DEFAULT,
        ge=100,
        le=10_000,
        description=(
            "Longest one transition of the OAuth refresh door (the conditional "
            "write of a refreshed token, the verified revocation) waits for its "
            "row, in milliseconds. The door writes on a session of its own, so a "
            "caller whose open transaction holds the row would otherwise wait on "
            "the door forever. Past the bound a write is abandoned (the caller is "
            "served the new token unstored) and a revocation is reported as a "
            "failure, never as a disconnection. Symptom if too low: legitimate "
            "brief contention loses a refreshed token's write. Symptom if too "
            "high: a caller holding its connector row waits that long."
        ),
    )
