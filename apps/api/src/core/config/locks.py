"""
Locks configuration module.

Contains settings for distributed locking (Redis-backed). Currently focused
on the OAuth refresh lock — a per-(user, connector) mutual exclusion that
prevents concurrent token refreshes from racing each other and burning the
refresh token.

Phase: v1.21 — Timeout centralization (Vague 2)
Created: 2026-05-15
Reference: docs/technical/TIMEOUT_REGISTRY.md
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import OAUTH_LOCK_TIMEOUT_SECONDS


class LocksSettings(BaseSettings):
    """Settings for distributed lock acquisition."""

    # ========================================================================
    # OAuth Refresh Lock
    # ========================================================================

    oauth_lock_timeout_seconds: int = Field(
        default=OAUTH_LOCK_TIMEOUT_SECONDS,
        ge=1,
        le=120,
        description=(
            "Maximum time a caller waits to acquire the per-(user, connector) "
            "OAuth refresh lock. Beyond this, the caller gives up and a "
            "Prometheus oauth_lock_timeout_total counter is incremented. "
            "Symptom if too low: legitimate concurrent refresh attempts "
            "fail and surface as transient OAuth errors. Symptom if too "
            "high: a hung refresh blocks unrelated requests for the same "
            "connector for a long time."
        ),
    )
