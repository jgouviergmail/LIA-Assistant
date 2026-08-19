"""Adaptive per-user threshold settings (lot 7, audit 2026-08-19).

The generic controller (``infrastructure/adaptive/threshold_controller``)
moves per-user similarity thresholds inside hard per-perimeter bounds toward
a target pass-rate band. These knobs govern the CONTROLLER (window, pace);
the per-perimeter bounds live with the perimeter registry, next to the code
that owns each threshold's semantics.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    ADAPTIVE_THRESHOLD_ADJUST_INTERVAL_HOURS_DEFAULT,
    ADAPTIVE_THRESHOLD_MIN_SAMPLES_DEFAULT,
    ADAPTIVE_THRESHOLD_STATE_TTL_DAYS_DEFAULT,
    ADAPTIVE_THRESHOLD_STEP_DEFAULT,
    ADAPTIVE_THRESHOLD_WINDOW_SIZE_DEFAULT,
    ADAPTIVE_THRESHOLDS_ENABLED_DEFAULT,
)


class AdaptiveSettings(BaseSettings):
    """Env-overridable settings for the adaptive threshold controller."""

    adaptive_thresholds_enabled: bool = Field(
        default=ADAPTIVE_THRESHOLDS_ENABLED_DEFAULT,
        description="Kill-switch: false freezes every perimeter to its static default.",
    )
    adaptive_threshold_window_size: int = Field(
        default=ADAPTIVE_THRESHOLD_WINDOW_SIZE_DEFAULT,
        ge=10,
        le=500,
        description="Rolling top-score samples kept per (user, perimeter).",
    )
    adaptive_threshold_min_samples: int = Field(
        default=ADAPTIVE_THRESHOLD_MIN_SAMPLES_DEFAULT,
        ge=5,
        le=500,
        description="Samples required before any adjustment may happen.",
    )
    adaptive_threshold_step: float = Field(
        default=ADAPTIVE_THRESHOLD_STEP_DEFAULT,
        gt=0.0,
        le=0.05,
        description="Single bounded adjustment step (hysteresis: one per interval).",
    )
    adaptive_threshold_adjust_interval_hours: float = Field(
        default=ADAPTIVE_THRESHOLD_ADJUST_INTERVAL_HOURS_DEFAULT,
        ge=1.0,
        le=168.0,
        description="Minimum hours between two adjustments of the same (user, perimeter).",
    )
    adaptive_threshold_state_ttl_days: int = Field(
        default=ADAPTIVE_THRESHOLD_STATE_TTL_DAYS_DEFAULT,
        ge=7,
        le=365,
        description="Sliding TTL of the per-user state key (refreshed on every "
        "write): deleted or abandoned accounts must not leave orphan keys.",
    )
