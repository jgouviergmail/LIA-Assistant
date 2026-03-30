"""
Pydantic schemas for the Interests domain API.

Schemas:
- InterestResponse: Interest data for API responses
- InterestCreate: Create a new interest manually
- InterestFeedbackRequest: Submit feedback on notification
- InterestSettingsResponse: User interest settings
- InterestSettingsUpdate: Update interest settings
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.interests.models import InterestCategory, InterestFeedback, InterestStatus

# =============================================================================
# Interest Schemas
# =============================================================================


class InterestResponse(BaseModel):
    """Interest data for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topic: str
    category: InterestCategory
    weight: float = Field(
        description="Computed effective weight (0.0-1.0) based on Bayesian signals and decay"
    )
    status: InterestStatus
    positive_signals: int
    negative_signals: int
    last_mentioned_at: datetime
    last_notified_at: datetime | None
    created_at: datetime


class InterestCreate(BaseModel):
    """Create a new interest manually."""

    topic: str = Field(
        min_length=2,
        max_length=200,
        description="Interest topic (e.g., 'machine learning', 'iOS development')",
    )
    category: InterestCategory = Field(
        default=InterestCategory.OTHER,
        description="Interest category",
    )


class InterestUpdate(BaseModel):
    """Update an existing interest (partial update)."""

    topic: str | None = Field(
        None,
        min_length=2,
        max_length=200,
        description="Interest topic (triggers embedding regeneration if changed)",
    )
    category: InterestCategory | None = Field(
        None,
        description="Interest category",
    )
    positive_signals: int | None = Field(
        None,
        ge=1,
        description="Positive signals count (min 1 for Bayesian prior)",
    )
    negative_signals: int | None = Field(
        None,
        ge=0,
        description="Negative signals count",
    )


class InterestFeedbackRequest(BaseModel):
    """Submit feedback on a notification."""

    feedback: Literal["thumbs_up", "thumbs_down", "block"] = Field(
        description="Feedback type: thumbs_up (positive), thumbs_down (negative), block (never notify)"
    )


class InterestListResponse(BaseModel):
    """List of interests with metadata."""

    interests: list[InterestResponse]
    total: int
    active_count: int
    blocked_count: int


# =============================================================================
# Settings Schemas
# =============================================================================


class InterestSettingsResponse(BaseModel):
    """User interest settings."""

    interests_enabled: bool = Field(
        description="Whether proactive interest notifications are enabled"
    )
    interests_notify_start_hour: int = Field(
        ge=0, le=23, description="Start hour for notifications (0-23)"
    )
    interests_notify_end_hour: int = Field(
        ge=0, le=23, description="End hour for notifications (0-23)"
    )
    interests_notify_min_per_day: int = Field(
        ge=1, le=10, description="Minimum notifications per day"
    )
    interests_notify_max_per_day: int = Field(
        ge=1, le=10, description="Maximum notifications per day"
    )


class InterestSettingsUpdate(BaseModel):
    """Update interest settings (partial update)."""

    interests_enabled: bool | None = None
    interests_notify_start_hour: int | None = Field(None, ge=0, le=23)
    interests_notify_end_hour: int | None = Field(None, ge=0, le=23)
    interests_notify_min_per_day: int | None = Field(None, ge=1, le=10)
    interests_notify_max_per_day: int | None = Field(None, ge=1, le=10)


# =============================================================================
# Notification Schemas
# =============================================================================


class InterestNotificationResponse(BaseModel):
    """Notification data for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    interest_id: UUID | None
    interest_topic: str | None
    source: str
    user_feedback: InterestFeedback | None
    created_at: datetime


class InterestNotificationListResponse(BaseModel):
    """List of notifications with metadata."""

    notifications: list[InterestNotificationResponse]
    total: int


# =============================================================================
# Category Schemas
# =============================================================================


class InterestCategoryResponse(BaseModel):
    """Available interest category."""

    value: str
    label: str
    description: str


class InterestCategoriesResponse(BaseModel):
    """List of available categories."""

    categories: list[InterestCategoryResponse]


# =============================================================================
# Extraction Internal Schemas (not exposed via API)
# =============================================================================


class ExtractedInterest(BaseModel):
    """Interest extracted from conversation by LLM.

    Supports create, update, and delete actions.
    Backward-compatible: if no 'action' field, defaults to 'create'.
    """

    action: Literal["create", "update", "delete"] = Field(
        default="create",
        description="Action type: create new, update existing, or delete existing.",
    )
    interest_id: str | None = Field(
        default=None,
        description="UUID of existing interest (required for update/delete).",
    )
    topic: str | None = Field(
        default=None,
        min_length=2,
        max_length=200,
        description="Interest topic description (required for create, optional for update).",
    )
    category: InterestCategory | None = Field(
        default=None,
        description="Interest category (required for create, optional for update).",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Extraction confidence score (required for create).",
    )


class ExtractionResult(BaseModel):
    """Result of interest extraction from conversation."""

    interests: list[ExtractedInterest] = Field(
        max_length=2,
        description="Extracted interests (max 2 per exchange)",
    )
