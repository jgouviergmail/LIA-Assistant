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

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    subject: str | None = Field(
        default=None,
        description="LLM-assigned subject label grouping related interests (ADR-131).",
    )


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
    run_id: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "Run identifier of the notification card the verdict came from, as "
            "carried in its archived metadata. When present the audit trail "
            "records the verdict on that exact notification, and only that "
            "card is marked as answered; when absent (older cards, or feedback "
            "given from the settings list) only the interest itself is updated "
            "— the audit is never attributed by guesswork."
        ),
    )

    @field_validator("run_id")
    @classmethod
    def blank_run_id_is_absent(cls, value: str | None) -> str | None:
        """Read a blank run_id as no run_id at all.

        An empty (or whitespace-only) string identifies nothing, and the two
        consumers of this field branch on it differently: the audit write tests
        truthiness, the archived-card write compares the value against stored
        metadata. Left as ``""`` they would disagree — the audit skipped, the
        card write narrowed to a run_id no row carries — and the verdict would
        reach the interest and nothing else, in silence.

        Normalising at the boundary keeps every consumer honest without each
        one remembering to write ``or None``.

        Args:
            value: The raw run_id, if the client sent one.

        Returns:
            The trimmed identifier, or None when it carries no information.
        """
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class InterestListResponse(BaseModel):
    """List of interests with metadata."""

    interests: list[InterestResponse]
    total: int
    active_count: int
    blocked_count: int
    dormant_count: int = Field(
        default=0,
        description="Number of dormant interests (low weight, awaiting reactivation)",
    )


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


class InterestNotificationHistoryItem(BaseModel):
    """One interest notification, as the settings history shows it.

    Deliberately the same shape as `HeartbeatNotificationResponse` minus the
    fields interests do not have: there is no priority (an interest nudge is
    never urgent) and the "source used" is a single content provider rather
    than a list of context sources.

    `content` is optional because the audit table only started keeping the
    message on 2026-08-03: an older row renders without its paragraph rather
    than with an invented one.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Notification identifier.")
    created_at: datetime = Field(description="When the notification was sent (UTC).")
    content: str | None = Field(
        None,
        description="Message sent to the user; absent for rows predating the column.",
    )
    source: str = Field(description="Content provider that produced it.")
    topic: str | None = Field(
        None,
        description="The interest it was about; absent when that interest was deleted.",
    )
    user_feedback: str | None = Field(
        None, description="thumbs_up | thumbs_down | block, or absent."
    )


class InterestNotificationHistoryResponse(BaseModel):
    """A page of interest notifications, with the EXACT total behind it."""

    notifications: list[InterestNotificationHistoryItem] = Field(default_factory=list)
    total: int = Field(
        description=(
            "Exact count over the whole set, never the page length (ADR-185): "
            "the panel states the cap instead of applying it in silence."
        )
    )


class InterestExplanation(BaseModel):
    """Why an interest weighs what it weighs — inputs AND coefficients.

    Published rather than summarised: the reader can recompute the number the
    ranking applies, which is the difference between an explanation and a
    reassurance. Deliberately carries no rank, no level and no comparison —
    a Beta mean IS an uncertainty estimate, and "two signals, so this is a
    guess" helps someone deciding whether to block a subject in a way no score
    ever could.
    """

    positive_signals: int = Field(ge=0, description="Reinforcements observed.")
    negative_signals: int = Field(ge=0, description="Rejections observed.")
    prior_alpha: float = Field(gt=0, description="Beta prior alpha (optimistic start).")
    prior_beta: float = Field(gt=0, description="Beta prior beta.")
    base_weight: float = Field(ge=0.0, le=1.0, description="Beta mean before any temporal decay.")
    decay_rate_per_day: float = Field(
        gt=0, description="Fraction of weight lost per day without a mention."
    )
    decay_floor: float = Field(
        gt=0,
        description=(
            "Floor under the decay. Without it a long-unmentioned interest "
            "would reach zero, never be notified, and therefore never be "
            "mentioned again."
        ),
    )
    days_since_last_mention: int = Field(ge=0, description="Days since the last mention.")
    effective_weight: float = Field(
        ge=0.0,
        le=1.0,
        description="What the ranking actually applies — base weight times decay.",
    )
    last_mentioned_at: datetime = Field(description="Last time the subject came up.")
    last_notified_at: datetime | None = Field(
        default=None, description="Last time LIA wrote about it; None if never."
    )
    status: str = Field(description="active / dormant / blocked.")
    dormant_since: datetime | None = Field(
        default=None, description="When it went dormant, if it did."
    )
