"""
Psyche Engine configuration module.

Contains settings for the dynamic psychological state system:
- Feature toggles (global enable, history snapshots)
- Mood dynamics (decay rates, circadian amplitude)
- Emotion parameters (decay rate, max active, sensitivity)
- Relationship parameters (warmth decay)
- Self-efficacy (Bayesian prior weight)
- Caching (Redis TTL)

Phase: evolution — Psyche Engine (Iteration 1)
Created: 2026-04-01
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    PSYCHE_AD_RELAXATION_DEFAULT,
    PSYCHE_APPRAISAL_SENSITIVITY_DEFAULT,
    PSYCHE_BASELINE_DAMPING_DEFAULT,
    PSYCHE_CACHE_TTL_SECONDS_DEFAULT,
    PSYCHE_CIRCADIAN_AMPLITUDE_DEFAULT,
    PSYCHE_EMBODIED_INJECTION_DEFAULT,
    PSYCHE_EMOTION_DECAY_RATE_DEFAULT,
    PSYCHE_EMOTION_MAX_ACTIVE_DEFAULT,
    PSYCHE_ENABLED_DEFAULT,
    PSYCHE_HISTORY_RETENTION_DAYS_DEFAULT,
    PSYCHE_MOOD_DECAY_RATE_DEFAULT,
    PSYCHE_RELATIONSHIP_WARMTH_DECAY_DEFAULT,
    PSYCHE_SELF_EFFICACY_PRIOR_WEIGHT_DEFAULT,
)


class PsycheSettings(BaseSettings):
    """Settings for the Psyche Engine (dynamic mood, emotions, relationship tracking)."""

    # ========================================================================
    # Feature Toggles (system-level, .env)
    # ========================================================================

    psyche_enabled: bool = Field(
        default=PSYCHE_ENABLED_DEFAULT,
        description=(
            "Global feature flag for Psyche Engine. "
            "When false, the entire domain is disabled (no router, no mood injection, no appraisal)."
        ),
    )

    psyche_history_snapshot_enabled: bool = Field(
        default=True,
        description=(
            "Enable psyche history snapshots for evolution tracking. "
            "When false, no snapshots are recorded (reduces DB writes)."
        ),
    )

    psyche_history_retention_days: int = Field(
        default=PSYCHE_HISTORY_RETENTION_DAYS_DEFAULT,
        ge=0,
        le=3650,
        description=(
            "Rolling retention window (days) for psyche history snapshots. "
            "One snapshot is written per message, so without a bound the table "
            "grows ~10k+ rows/year for an active user. Snapshots older than this "
            "are purged on write, per user. 0 disables retention (keep forever)."
        ),
    )

    psyche_embodied_injection: bool = Field(
        default=PSYCHE_EMBODIED_INJECTION_DEFAULT,
        description=(
            "Expression layer (ADR-104 A-E): when true, the main response uses the "
            "embodied voice injection (concrete form grammar). When false, roll back to "
            "the legacy graduated adjective directives."
        ),
    )

    # ========================================================================
    # Mood Dynamics
    # ========================================================================

    psyche_mood_decay_rate: float = Field(
        default=PSYCHE_MOOD_DECAY_RATE_DEFAULT,
        ge=0.01,
        le=1.0,
        description=(
            "Mood decay rate toward baseline per hour (exponential). "
            "Higher values = faster return to baseline. "
            "0.1 means ~63% return in 10 hours."
        ),
    )

    psyche_circadian_amplitude: float = Field(
        default=PSYCHE_CIRCADIAN_AMPLITUDE_DEFAULT,
        ge=0.0,
        le=0.3,
        description=(
            "Circadian modulation amplitude on mood pleasure baseline. "
            "0.0 = no circadian effect. 0.08 = subtle midday boost."
        ),
    )

    psyche_ad_relaxation: float = Field(
        default=PSYCHE_AD_RELAXATION_DEFAULT,
        ge=0.0,
        le=1.0,
        description=(
            "De-saturation: fraction of the mood→baseline gap closed on every "
            "interaction (before the emotion push). Counters within-burst arousal/"
            "dominance ratcheting when temporal decay is ~0. 0.0 disables it."
        ),
    )

    psyche_baseline_damping: float = Field(
        default=PSYCHE_BASELINE_DAMPING_DEFAULT,
        ge=0.0,
        le=1.0,
        description=(
            "De-saturation: multiplier applied to the computed PAD baseline "
            "magnitude, pulling every personality's resting point toward neutral "
            "while preserving relative differences. 1.0 = raw Mehrabian mapping."
        ),
    )

    # ========================================================================
    # Emotion Parameters
    # ========================================================================

    psyche_emotion_decay_rate: float = Field(
        default=PSYCHE_EMOTION_DECAY_RATE_DEFAULT,
        ge=0.05,
        le=1.0,
        description=(
            "Emotion intensity decay rate per hour (exponential). "
            "0.3 means emotion loses ~26% intensity per hour."
        ),
    )

    psyche_emotion_max_active: int = Field(
        default=PSYCHE_EMOTION_MAX_ACTIVE_DEFAULT,
        ge=1,
        le=10,
        description="Maximum simultaneous active emotions. Weakest is evicted when exceeded.",
    )

    psyche_appraisal_sensitivity: float = Field(
        default=PSYCHE_APPRAISAL_SENSITIVITY_DEFAULT,
        ge=0.1,
        le=1.0,
        description=(
            "Sensitivity multiplier for appraisal → emotion intensity. "
            "Higher values = stronger emotional reactions to stimuli."
        ),
    )

    # ========================================================================
    # Relationship Parameters
    # ========================================================================

    psyche_relationship_warmth_decay_rate: float = Field(
        default=PSYCHE_RELATIONSHIP_WARMTH_DECAY_DEFAULT,
        ge=0.001,
        le=0.1,
        description=(
            "Warmth decay rate per hour of absence. "
            "0.02 means warmth drops ~50% in ~35 hours of no interaction."
        ),
    )

    # ========================================================================
    # Self-Efficacy
    # ========================================================================

    psyche_self_efficacy_prior_weight: float = Field(
        default=PSYCHE_SELF_EFFICACY_PRIOR_WEIGHT_DEFAULT,
        ge=1.0,
        le=20.0,
        description=(
            "Bayesian prior weight for self-efficacy updates. "
            "Higher values = slower change (more conservative)."
        ),
    )

    # ========================================================================
    # Caching
    # ========================================================================

    psyche_cache_ttl_seconds: int = Field(
        default=PSYCHE_CACHE_TTL_SECONDS_DEFAULT,
        ge=60,
        le=3600,
        description="Redis cache TTL for psyche state (seconds).",
    )
