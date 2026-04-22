"""
Health Metrics configuration module.

Contains settings for the Health Metrics feature (iPhone Shortcuts ingestion
of heart rate, step counts, …) exposed via a token-authenticated REST
endpoint, persisted in PostgreSQL with idempotent upsert, and visualized
in the Settings UI.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    HEALTH_METRICS_BASELINE_MIN_DAYS_DEFAULT,
    HEALTH_METRICS_ENABLED_DEFAULT,
    HEALTH_METRICS_HEART_RATE_MAX,
    HEALTH_METRICS_HEART_RATE_MIN,
    HEALTH_METRICS_MAX_SAMPLES_PER_REQUEST_DEFAULT,
    HEALTH_METRICS_RATE_LIMIT_PER_HOUR_DEFAULT,
    HEALTH_METRICS_STEPS_MAX,
    HEALTH_METRICS_STEPS_MIN,
    HEALTH_METRICS_VARIATION_DAILY_DELTA_PCT_DEFAULT,
    HEALTH_METRICS_VARIATION_MIN_DAYS_DEFAULT,
    HEALTH_METRICS_VARIATION_MIN_DELTA_PCT_DEFAULT,
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
        le=3600,
        description=(
            "Maximum ingestion requests allowed per hour per token. "
            "Default 60/hour (1 per minute), covers bursts when the iPhone "
            "is unlocked and Shortcuts catches up on several batches."
        ),
    )

    health_metrics_max_samples_per_request: int = Field(
        default=HEALTH_METRICS_MAX_SAMPLES_PER_REQUEST_DEFAULT,
        ge=1,
        le=10_000,
        description=(
            "Maximum number of samples accepted in a single ingest request. "
            "Exceeding this returns HTTP 413. Default 1000 (covers a full "
            "day of 5-minute HR samples with margin)."
        ),
    )

    # ========================================================================
    # Physiological validation bounds (mixed per-sample — out-of-range rejected)
    # ========================================================================

    health_metrics_heart_rate_min: int = Field(
        default=HEALTH_METRICS_HEART_RATE_MIN,
        ge=0,
        le=300,
        description=("Minimum plausible heart rate (bpm). Samples below are rejected."),
    )

    health_metrics_heart_rate_max: int = Field(
        default=HEALTH_METRICS_HEART_RATE_MAX,
        ge=0,
        le=300,
        description=("Maximum plausible heart rate (bpm). Samples above are rejected."),
    )

    health_metrics_steps_min: int = Field(
        default=HEALTH_METRICS_STEPS_MIN,
        ge=0,
        le=1_000_000,
        description=("Minimum plausible per-sample step count. Samples below are rejected."),
    )

    health_metrics_steps_max: int = Field(
        default=HEALTH_METRICS_STEPS_MAX,
        ge=0,
        le=1_000_000,
        description=(
            "Maximum plausible per-sample step count "
            "(NOT a daily cap — it bounds one inter-sample interval). "
            "Samples above are rejected."
        ),
    )

    # ========================================================================
    # Baseline + recent-variations detection (used by assistant agents)
    # ========================================================================

    health_metrics_baseline_min_days: int = Field(
        default=HEALTH_METRICS_BASELINE_MIN_DAYS_DEFAULT,
        ge=1,
        le=90,
        description=(
            "Minimum number of distinct days of data before switching the "
            "baseline mode from ``bootstrap`` (median of all available data) "
            "to ``rolling`` (28-day rolling median). Below this threshold, "
            "deltas are still computed but labeled as bootstrap in the tool "
            "response so the LLM can qualify its statements accordingly."
        ),
    )

    health_metrics_variation_min_days: int = Field(
        default=HEALTH_METRICS_VARIATION_MIN_DAYS_DEFAULT,
        ge=1,
        le=14,
        description=(
            "Minimum consecutive-day streak length for a variation to be "
            "flagged as notable by ``detect_recent_variations``."
        ),
    )

    health_metrics_variation_min_delta_pct: float = Field(
        default=HEALTH_METRICS_VARIATION_MIN_DELTA_PCT_DEFAULT,
        ge=1.0,
        le=100.0,
        description=(
            "Minimum absolute average delta (percent vs baseline) across the "
            "streak for a variation to be flagged as notable."
        ),
    )

    health_metrics_variation_daily_delta_pct: float = Field(
        default=HEALTH_METRICS_VARIATION_DAILY_DELTA_PCT_DEFAULT,
        ge=1.0,
        le=100.0,
        description=(
            "Per-day delta threshold (percent vs baseline) for a day to be "
            "counted as part of a directional streak."
        ),
    )
