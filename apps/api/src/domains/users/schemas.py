"""
Users domain schemas (Pydantic models for API).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.constants import (
    IMAGE_GENERATION_OUTPUT_FORMAT_DEFAULT,
    USER_FONT_SIZE_MAX_PX,
    USER_FONT_SIZE_MIN_PX,
)
from src.core.exchange_rhythm import ExchangeRhythm
from src.core.i18n import _
from src.domains.shared.schemas import (
    FontFamilyValidatorMixin,
    ImageGenerationValidatorMixin,
    LanguageValidatorMixin,
    ThemeValidatorMixin,
    TimezoneValidatorMixin,
    UserBase,
)


class UserUpdate(
    BaseModel,
    TimezoneValidatorMixin,
    LanguageValidatorMixin,
    ThemeValidatorMixin,
    FontFamilyValidatorMixin,
    ImageGenerationValidatorMixin,
):
    """Schema for updating user profile.

    SEC-005: ``email`` is deliberately NOT part of this schema. The generic
    ``PATCH /users/{user_id}`` is guarded by the session cookie and an ownership
    check only — no recent re-authentication, no proof of owning the new
    mailbox, no notification to the previous address, no session revocation.
    Allowing the address to change there turns a stolen session into a permanent
    account takeover: the attacker swaps the address, then drives the standard
    password-recovery flow.

    Changing the address needs its own flow (recent step-up via
    ``require_recent_step_up``, a single-use token hashed at rest, confirmation
    from the new mailbox, notification of the old one). Until that exists the
    address is immutable through the API, which is the safe default — and no UI
    ever exposed the field, so nothing regresses.

    Pydantic's default ``extra="ignore"`` means a client still sending ``email``
    is silently ignored rather than erroring: the address simply does not change.
    """

    full_name: str | None = Field(None, description="User full name")
    picture_url: str | None = Field(None, description="Profile picture URL")
    timezone: str | None = Field(None, description="User's IANA timezone")
    language: str | None = Field(
        None,
        description=(
            "User's preferred language for emails and notifications (fr, en, es, de, it, zh-CN)"
        ),
    )
    personality_id: UUID | None = Field(None, description="User's preferred LLM personality ID")
    theme: str | None = Field(
        None,
        description="User display mode: 'light', 'dark', or 'system'",
    )
    color_theme: str | None = Field(
        None,
        description="User color theme: 'default', 'ocean', 'forest', 'sunset', 'slate'",
    )
    font_family: str | None = Field(
        None,
        description="User font family: 'system', 'noto-sans', 'plus-jakarta-sans', 'ibm-plex-sans', 'geist', 'source-sans-pro', 'merriweather', 'libre-baskerville', 'fira-code'",
    )
    # Strict: the slider sends integers; a string or a boolean is a client defect.
    font_size: int | None = Field(
        None,
        strict=True,
        ge=USER_FONT_SIZE_MIN_PX,
        le=USER_FONT_SIZE_MAX_PX,
        description="Interface text size in CSS px at the browser's default root size",
    )

    # Image Generation preferences
    image_generation_enabled: bool | None = Field(
        None, description="Enable AI image generation feature"
    )
    image_generation_default_quality: str | None = Field(
        None, description="Preferred image quality, in the configured model's vocabulary"
    )
    image_generation_default_size: str | None = Field(
        None, description="Preferred image size (WIDTHxHEIGHT)"
    )
    image_generation_output_format: str | None = Field(
        None,
        description="Format generated and edited images are delivered in: 'png', 'jpeg', 'webp'",
    )
    image_generation_prompt_enhancement: bool | None = Field(
        None,
        description=(
            "Rewrite image prompts with recognised prompting techniques before "
            "generation (ADR-315); inert while the operator withdraws it"
        ),
    )

    # ADR-311: strict on write — the two rhythms, dumped as exact strings.
    exchange_rhythm: ExchangeRhythm | None = Field(
        None,
        description=(
            "Exchange rhythm: 'frequent' (every tool bound, the prompt shaped for the "
            "next turn's cache) or 'occasional' (tools chosen by relevance)"
        ),
    )

    model_config = {"from_attributes": True, "use_enum_values": True}

    @field_validator("theme", "color_theme", "font_family", "font_size", mode="before")
    @classmethod
    def refuse_explicit_null_display_preference(cls, value: object) -> object:
        """Refuse a display preference SENT as null: its column is NOT NULL.

        ``exclude_unset`` keeps a key the client sent, so a null used to reach the
        flush and answer a 500. An omitted field is never validated, so it stays
        unset and unwritten.

        Raises:
            ValueError: When the value is an explicit null.
        """
        if value is None:
            raise ValueError("must not be null")
        return value


class UserProfile(UserBase, LanguageValidatorMixin):
    """Schema for user profile response with additional user-specific fields."""

    # Additional fields not in UserBase
    # Required: a profile is read from a row whose language is NOT NULL, and a
    # known person's language never falls back to the requester's (ADR-323).
    language: str = Field(
        ...,
        description="User's preferred language (fr, en, es, de, it, zh-CN)",
    )
    personality_id: UUID | None = Field(None, description="User's preferred LLM personality ID")
    home_address: str | None = Field(
        None, description="User's home address (decrypted for display)"
    )

    # Image Generation preferences
    image_generation_enabled: bool = Field(default=False, description="AI image generation enabled")
    image_generation_default_quality: str = Field(
        default="medium", description="Default image quality"
    )
    image_generation_default_size: str = Field(
        default="1024x1024", description="Default image size"
    )
    image_generation_output_format: str = Field(
        default=IMAGE_GENERATION_OUTPUT_FORMAT_DEFAULT,
        description="Format generated and edited images are delivered in",
    )


class UserListResponse(BaseModel):
    """Schema for paginated user list response."""

    users: list[UserProfile] = Field(..., description="List of users")
    total: int = Field(..., description="Total number of users")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")


# ========== ADMIN - USER STATISTICS ==========


class UserStatisticsData(BaseModel):
    """Schema for user statistics (tokens, messages)."""

    last_login: datetime | None = Field(None, description="Last login timestamp")
    total_messages: int = Field(0, description="Total messages sent")
    total_prompt_tokens: int = Field(0, description="Total input tokens (IN)")
    total_completion_tokens: int = Field(0, description="Total output tokens (OUT)")
    total_cached_tokens: int = Field(0, description="Total cached tokens (CACHE)")

    @property
    def total_tokens(self) -> int:
        """Total tokens (IN + OUT + CACHE)."""
        return self.total_prompt_tokens + self.total_completion_tokens + self.total_cached_tokens

    model_config = {"from_attributes": True}


class UserProfileWithStats(UserProfile):
    """Extended user profile with statistics for admin view."""

    last_login: datetime | None = Field(None, description="Last login timestamp")
    last_message_at: datetime | None = Field(None, description="Last message sent timestamp")
    # Lifetime totals
    total_messages: int = Field(0, description="Total messages sent")
    total_tokens: int = Field(0, description="Total tokens (IN + OUT + CACHE)")
    tokens_in: int = Field(0, description="Total input tokens")
    tokens_out: int = Field(0, description="Total output tokens")
    tokens_cache: int = Field(0, description="Total cached tokens")
    total_cost_eur: float = Field(0.0, description="Total cost in EUR")
    total_google_api_requests: int = Field(0, description="Total Google API requests")
    # Current billing cycle
    cycle_messages: int = Field(0, description="Messages sent this cycle")
    cycle_tokens: int = Field(0, description="Tokens used this cycle")
    cycle_google_api_requests: int = Field(0, description="Google API requests this cycle")
    cycle_cost_eur: float = Field(0.0, description="Cost in EUR this cycle")
    # Other stats
    active_connectors_count: int = Field(0, description="Number of active connectors")
    memories_count: int = Field(0, description="Number of memories stored")
    interests_count: int = Field(0, description="Number of interests")
    skills_count: int = Field(0, description="Number of user-imported skills")
    mcp_servers_count: int = Field(0, description="Number of user MCP servers")
    scheduled_actions_count: int = Field(0, description="Number of scheduled actions")
    rag_spaces_count: int = Field(0, description="Number of RAG knowledge spaces")
    is_usage_blocked: bool = Field(False, description="Whether user is usage-blocked by admin")
    # The switches ``UserProfile`` does not carry (``admin_columns``). Required:
    # a builder that forgot one must fail, never report a default.
    psyche_enabled: bool = Field(..., description="Psyche engine (mood, emotions) enabled")
    psyche_display_avatar: bool = Field(..., description="Emotional avatar shown in the chat")
    habits_enabled: bool = Field(..., description="Learned habits enabled")
    journals_enabled: bool = Field(..., description="Personal journals enabled")
    journal_consolidation_enabled: bool = Field(
        ..., description="Periodic journal consolidation enabled"
    )
    journal_consolidation_with_history: bool = Field(
        ..., description="Journal consolidation may read the conversation history"
    )
    phone_rich_context_enabled: bool = Field(
        ..., description="The chat's context is carried into the person's own calls"
    )
    heartbeat_enabled: bool = Field(..., description="Proactive notifications enabled")
    interests_enabled: bool = Field(..., description="Interest notifications enabled")
    relation_debrief_enabled: bool = Field(..., description="Relationship debriefs enabled")
    discovery_enabled: bool = Field(..., description="Findable by peer discovery")
    peer_email_visible: bool = Field(..., description="Real address shown to connections")
    deleted_at: datetime | None = Field(
        None, description="Account deletion timestamp (None = not deleted)"
    )
    is_deleted: bool = Field(False, description="Whether account is soft-deleted (data purged)")

    model_config = {"from_attributes": True}


class UserListWithStatsResponse(BaseModel):
    """Schema for paginated user list with statistics response (admin)."""

    users: list[UserProfileWithStats] = Field(..., description="List of users with statistics")
    total: int = Field(..., description="Total number of users")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")


# ========== ADMIN - USER MANAGEMENT ==========


class UserSearchParams(BaseModel):
    """Query parameters for searching users (admin)."""

    q: str | None = Field(None, description="Search query (email or full name)")
    is_active: bool | None = Field(None, description="Filter by active status")
    is_verified: bool | None = Field(None, description="Filter by verified status")
    is_superuser: bool | None = Field(None, description="Filter by superuser status")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(10, ge=1, le=100, description="Items per page")
    sort_by: str = Field(
        "created_at",
        description="Sort column, a key of ``admin_columns.ADMIN_USER_SORT_KEYS``.",
    )
    sort_order: str = Field("desc", description="Sort order (asc or desc)")


class UserActivationUpdate(BaseModel):
    """Schema for activating/deactivating a user (admin)."""

    is_active: bool = Field(..., description="Activate or deactivate user")
    reason: str | None = Field(
        None, description="Reason for deactivation (required when deactivating)"
    )

    @model_validator(mode="after")
    def require_a_deactivation_reason(self) -> UserActivationUpdate:
        """A deactivation states its reason: the account holder is told it.

        Checked on the whole model — a field validator never runs on an omitted
        field, so ``{"is_active": false}`` used to pass without one. The refusal
        speaks the declared language: the acting administrator reads it.
        """
        if not self.is_active and not (self.reason and self.reason.strip()):
            raise ValueError(_("A deactivation must state its reason."))
        return self


class UserActivationResponse(BaseModel):
    """Schema for user activation/deactivation response with email notification status."""

    user: UserProfile = Field(..., description="Updated user profile")
    email_notification_sent: bool = Field(
        ..., description="Whether email notification was sent successfully"
    )
    email_notification_error: str | None = Field(
        None, description="Error message if email notification failed"
    )


# ========== ACCOUNT DELETION (Admin) ==========


class AccountDeletionRequest(BaseModel):
    """Request body for account deletion (soft-delete with data purge)."""

    reason: str | None = Field(
        None,
        max_length=500,
        description="Admin-provided reason for account deletion.",
    )


class AccountDeletionResponse(BaseModel):
    """Response for account deletion with purge counts per table."""

    user_id: UUID = Field(..., description="Deleted user ID")
    email: str = Field(..., description="User email (preserved for billing)")
    deleted_at: datetime = Field(..., description="Deletion timestamp")
    counts: dict[str, int] = Field(..., description="Number of deleted rows per table/resource")


# ========== AUTOCOMPLETE (Admin) ==========


class UserAutocompleteItem(BaseModel):
    """Simplified user item for autocomplete suggestions."""

    id: UUID = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    full_name: str | None = Field(None, description="User full name")
    is_active: bool = Field(..., description="Whether user is active")

    model_config = ConfigDict(from_attributes=True)


class UserAutocompleteResponse(BaseModel):
    """Response for user autocomplete suggestions."""

    users: list[UserAutocompleteItem] = Field(..., description="List of matching users")
    total: int = Field(..., description="Total number of matches (may be limited)")


# ========== HOME LOCATION ==========


class HomeLocationData(BaseModel):
    """Schema for home location data (decrypted from database)."""

    address: str = Field(..., max_length=500, description="Human-readable address")
    lat: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    lon: float = Field(..., ge=-180, le=180, description="Longitude coordinate")
    place_id: str | None = Field(
        default=None, max_length=100, description="Google Place ID (optional)"
    )

    model_config = {"from_attributes": True}


class HomeLocationUpdate(BaseModel):
    """Request schema for setting user's home location."""

    address: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Human-readable address from Places API",
    )
    lat: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    lon: float = Field(..., ge=-180, le=180, description="Longitude coordinate")
    place_id: str | None = Field(
        default=None, max_length=100, description="Google Place ID (optional)"
    )

    model_config = {"from_attributes": True}


class HomeLocationResponse(BaseModel):
    """Response schema for home location endpoint."""

    address: str = Field(..., description="Human-readable address")
    lat: float = Field(..., description="Latitude coordinate")
    lon: float = Field(..., description="Longitude coordinate")
    place_id: str | None = Field(default=None, description="Google Place ID")

    model_config = {"from_attributes": True}
