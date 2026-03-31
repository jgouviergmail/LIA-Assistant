"""
Users domain schemas (Pydantic models for API).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from src.core.field_names import FIELD_IS_ACTIVE
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
    """Schema for updating user profile."""

    email: EmailStr | None = Field(None, description="User email address")
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

    # Image Generation preferences
    image_generation_enabled: bool | None = Field(
        None, description="Enable AI image generation feature"
    )
    image_generation_default_quality: str | None = Field(
        None, description="Default image quality: 'low', 'medium', 'high'"
    )
    image_generation_default_size: str | None = Field(
        None, description="Default image size: '1024x1024', '1536x1024', '1024x1536'"
    )
    image_generation_output_format: str | None = Field(
        None, description="Default output format: 'png', 'jpeg', 'webp'"
    )

    model_config = {"from_attributes": True}


class UserProfile(UserBase, LanguageValidatorMixin):
    """Schema for user profile response with additional user-specific fields."""

    # Additional fields not in UserBase
    language: str = Field(
        default="fr", description="User's preferred language (fr, en, es, de, it)"
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
    image_generation_output_format: str = Field(default="png", description="Default output format")


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
        "created_at", description="Sort column (email, full_name, created_at, is_active)"
    )
    sort_order: str = Field("desc", description="Sort order (asc or desc)")


class UserActivationUpdate(BaseModel):
    """Schema for activating/deactivating a user (admin)."""

    is_active: bool = Field(..., description="Activate or deactivate user")
    reason: str | None = Field(
        None, description="Reason for deactivation (required when deactivating)"
    )

    @field_validator("reason")
    @classmethod
    def validate_deactivation_reason(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Require reason when deactivating user."""
        is_active = info.data.get(FIELD_IS_ACTIVE)
        if is_active is False and not v:
            raise ValueError("reason is required when deactivating a user")
        return v


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
