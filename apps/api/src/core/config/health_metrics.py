"""
Health Metrics configuration module.

Contains settings for the Health Metrics feature (iPhone Shortcuts ingestion
of heart rate, per-period step count, …) exposed via a token-authenticated
REST endpoint, persisted in PostgreSQL, and visualized in the Settings UI.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    HEALTH_METRICS_ENABLED_DEFAULT,
    HEALTH_METRICS_HEART_RATE_MAX,
    HEALTH_METRICS_HEART_RATE_MIN,
    HEALTH_METRICS_RATE_LIMIT_PER_HOUR_DEFAULT,
    HEALTH_METRICS_STEPS_MAX,
    HEALTH_METRICS_STEPS_MIN,
)


class HealthMetricsSettings(BaseSettings):
    """Settings for the Health Metrics ingestion and visualization feature."""

    # ========================================================================
    # Feature Toggles
    # ========================================================================

    health_metrics_enabled: bool = Field(
        default=HEALTH_METRICS_ENABLED_DEFAULT,
        description=(
            "Global feature flag for Health Metrics. "
            "When false, the entire domain is disabled (no router, no ingest, no UI)."
        ),
    )

    # ========================================================================
    # Ingestion
    # ========================================================================

    health_metrics_rate_limit_per_hour: int = Field(
        default=HEALTH_METRICS_RATE_LIMIT_PER_HOUR_DEFAULT,
        ge=1,
        le=120,
        description=(
            "Maximum ingestion requests allowed per hour per token. "
            "Default 5/hour (iPhone Shortcut sends once per hour, large safety margin)."
        ),
    )

    # ========================================================================
    # Physiological validation bounds (mixed validation — out-of-range → NULL)
    # ========================================================================

    health_metrics_heart_rate_min: int = Field(
        default=HEALTH_METRICS_HEART_RATE_MIN,
        ge=0,
        le=300,
        description=(
            "Minimum plausible heart rate (bpm). " "Values below are stored as NULL + warning log."
        ),
    )

    health_metrics_heart_rate_max: int = Field(
        default=HEALTH_METRICS_HEART_RATE_MAX,
        ge=0,
        le=300,
        description=(
            "Maximum plausible heart rate (bpm). " "Values above are stored as NULL + warning log."
        ),
    )

    health_metrics_steps_min: int = Field(
        default=HEALTH_METRICS_STEPS_MIN,
        ge=0,
        le=1_000_000,
        description=(
            "Minimum plausible per-sample step count. "
            "Values below are stored as NULL + warning log."
        ),
    )

    health_metrics_steps_max: int = Field(
        default=HEALTH_METRICS_STEPS_MAX,
        ge=0,
        le=1_000_000,
        description=(
            "Maximum plausible per-sample step count "
            "(NOT a daily cap — it bounds one ingestion window). "
            "Values above are stored as NULL + warning log."
        ),
    )
