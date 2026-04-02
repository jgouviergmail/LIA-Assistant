"""
Pydantic v2 schemas for the Psyche domain.

Defines request/response models for API endpoints and internal data transfer.
Follows the project convention: separate schemas for create, update, and response.

Phase: evolution — Psyche Engine (Iteration 1)
Created: 2026-04-01
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PsycheStateSummary(BaseModel):
    """Lightweight psyche state summary for SSE done metadata.

    Piggybacked on the SSE done event to update the frontend mood ring
    without requiring a separate API call.
    """

    mood_label: str = Field(description="Current mood label (e.g., 'serene', 'curious').")
    mood_color: str = Field(description="Hex color for mood ring (colorblind-safe).")
    mood_pleasure: float = Field(description="PAD Pleasure [-1, +1].")
    mood_arousal: float = Field(description="PAD Arousal [-1, +1].")
    mood_dominance: float = Field(description="PAD Dominance [-1, +1].")
    active_emotion: str | None = Field(description="Dominant active emotion name or null.")
    emotion_intensity: float = Field(description="Dominant emotion intensity [0, 1].")
    relationship_stage: str = Field(description="Current relationship stage.")


class PsycheSummaryResponse(BaseModel):
    """LLM-generated natural language summary of the current psyche state."""

    summary: str = Field(description="LLM-generated summary of the psyche state in user language.")


class PsycheStateResponse(BaseModel):
    """Full psyche state response for API endpoints.

    Contains all dynamic state fields plus computed expression profile.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Psyche state record ID.")
    user_id: UUID = Field(description="User ID.")

    # Big Five traits
    trait_openness: float = Field(description="Big Five Openness [0, 1].")
    trait_conscientiousness: float = Field(description="Big Five Conscientiousness [0, 1].")
    trait_extraversion: float = Field(description="Big Five Extraversion [0, 1].")
    trait_agreeableness: float = Field(description="Big Five Agreeableness [0, 1].")
    trait_neuroticism: float = Field(description="Big Five Neuroticism [0, 1].")

    # Mood (PAD)
    mood_pleasure: float = Field(description="PAD Pleasure [-1, +1].")
    mood_arousal: float = Field(description="PAD Arousal [-1, +1].")
    mood_dominance: float = Field(description="PAD Dominance [-1, +1].")
    mood_label: str = Field(
        default="neutral",
        description="Computed mood label.",
    )
    mood_color: str = Field(default="#9ca3af", description="Hex color for mood ring.")

    # Emotions
    active_emotions: list[ActiveEmotionResponse] = Field(
        default_factory=list,
        description="Active emotions with intensity and timestamp.",
    )

    # Relationship
    relationship_stage: str = Field(
        description="Current stage: ORIENTATION/EXPLORATORY/AFFECTIVE/STABLE.",
    )
    relationship_depth: float = Field(description="Depth [0, 1].")
    relationship_warmth_active: float = Field(description="Active warmth [0, 1].")
    relationship_trust: float = Field(description="Trust [0, 1].")
    relationship_interaction_count: int = Field(description="Total non-trivial interactions.")

    # Drives
    drive_curiosity: float = Field(description="Curiosity drive [0, 1].")
    drive_engagement: float = Field(description="Engagement drive [0, 1].")

    # Self-efficacy
    self_efficacy: dict[str, Any] = Field(
        default_factory=dict,
        description="Self-efficacy per domain {domain: {score, weight}}.",
    )

    # Timestamps
    created_at: datetime = Field(description="Creation timestamp (UTC).")
    updated_at: datetime = Field(description="Last update timestamp (UTC).")


class PsycheExpressionResponse(BaseModel):
    """Current compiled expression profile (computed, not stored)."""

    mood_label: str = Field(description="Current mood label.")
    mood_intensity: str = Field(
        description="Mood intensity: slightly/moderately/noticeably/strongly.",
    )
    active_emotions: list[dict[str, Any]] = Field(
        default_factory=list, description="Top active emotions."
    )
    relationship_stage: str = Field(description="Current relationship stage.")
    warmth_label: str = Field(description="Warmth label: cool/neutral/warm/very warm.")
    drive_curiosity: float = Field(description="Curiosity drive [0, 1].")
    drive_engagement: float = Field(description="Engagement drive [0, 1].")


class PsycheSettingsResponse(BaseModel):
    """User psyche preferences for settings UI."""

    psyche_enabled: bool = Field(description="Whether psyche engine is enabled for this user.")
    psyche_display_avatar: bool = Field(
        description="Whether emotional avatar is displayed in chat.",
    )
    psyche_sensitivity: int = Field(description="Emotional expressiveness (0-100).")
    psyche_stability: int = Field(description="Mood stability (0-100).")


class PsycheSettingsUpdate(BaseModel):
    """Partial update for user psyche preferences."""

    psyche_enabled: bool | None = Field(None, description="Enable/disable psyche engine.")
    psyche_display_avatar: bool | None = Field(
        None,
        description="Show/hide emotional avatar in chat.",
    )
    psyche_sensitivity: int | None = Field(
        None,
        ge=0,
        le=100,
        description="Expressiveness (0-100).",
    )
    psyche_stability: int | None = Field(
        None,
        ge=0,
        le=100,
        description="Mood stability (0-100).",
    )


class PsycheResetRequest(BaseModel):
    """Request to reset psyche state."""

    level: Literal["soft", "full", "purge"] = Field(
        description=(
            "Reset level: "
            "soft = reset mood + emotions only; "
            "full = reset everything except relationship; "
            "purge = delete entire state (GDPR)."
        ),
    )


class PsycheResetResponse(BaseModel):
    """Response after psyche state reset."""

    status: str = Field(description="Reset status ('reset').")
    level: str = Field(description="Reset level applied ('soft', 'full', 'purge').")


class ActiveEmotionResponse(BaseModel):
    """Single active emotion in API responses."""

    name: str = Field(description="Emotion name (e.g., 'joy', 'curiosity').")
    intensity: float = Field(description="Emotion intensity [0, 1].")
    triggered_at: str | None = Field(None, description="ISO 8601 timestamp when triggered.")


class PsycheHistoryEntry(BaseModel):
    """Single psyche history snapshot for the evolution dashboard."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Snapshot ID.")
    snapshot_type: str = Field(description="Type: message, session_end, daily, weekly_reflection.")
    mood_pleasure: float = Field(description="PAD Pleasure at snapshot time.")
    mood_arousal: float = Field(description="PAD Arousal at snapshot time.")
    mood_dominance: float = Field(description="PAD Dominance at snapshot time.")
    dominant_emotion: str | None = Field(description="Dominant emotion at snapshot time.")
    relationship_stage: str = Field(description="Relationship stage at snapshot time.")
    trait_snapshot: dict[str, Any] | None = Field(description="Big Five traits at snapshot time.")
    created_at: datetime = Field(description="Snapshot timestamp.")
