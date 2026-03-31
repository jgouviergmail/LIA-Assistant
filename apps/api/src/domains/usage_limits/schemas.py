"""
Usage limits domain schemas.

Pydantic v2 request/response schemas for per-user usage limit management.
Separate schemas for user-facing (/me) and admin endpoints.

Phase: evolution — Per-User Usage Limits
Created: 2026-03-21
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import USAGE_LIMIT_BLOCKED_REASON_MAX_LENGTH

# ============================================================================
# Enums
# ============================================================================


class UsageLimitStatus(str, Enum):
    """Usage limit enforcement status for a user."""

    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    BLOCKED_LIMIT = "blocked_limit"
    BLOCKED_MANUAL = "blocked_manual"
    BLOCKED_ACCOUNT = "blocked_account"


# ============================================================================
# Shared schemas
# ============================================================================


class LimitDetail(BaseModel):
    """Single limit dimension with current usage and configured limit.

    Used in both user-facing and admin responses to represent
    the state of one limit dimension (e.g., cycle tokens).
    """

    current: int | float = Field(description="Current usage value for this dimension.")
    limit: int | float | None = Field(description="Configured limit value. None means unlimited.")
    usage_pct: float | None = Field(
        description="Usage percentage (0-100). None if limit is unlimited."
    )
    exceeded: bool = Field(description="Whether this limit has been exceeded.")


# ============================================================================
# User-facing response schemas
# ============================================================================


class UserUsageLimitResponse(BaseModel):
    """Usage limit data for the current user (/me endpoint).

    Contains all limit dimensions with current usage, plus cycle boundaries.
    """

    model_config = ConfigDict(from_attributes=True)

    status: UsageLimitStatus = Field(description="Overall enforcement status.")
    is_blocked: bool = Field(description="Whether the user is currently blocked (any reason).")
    blocked_reason: str | None = Field(
        description="Reason for blocking (manual block or limit exceeded)."
    )

    # Per-cycle limits
    cycle_tokens: LimitDetail = Field(description="Token usage vs cycle limit.")
    cycle_messages: LimitDetail = Field(description="Message count vs cycle limit.")
    cycle_cost: LimitDetail = Field(description="Cost (EUR) vs cycle limit.")

    # Absolute limits
    absolute_tokens: LimitDetail = Field(description="Token usage vs absolute limit.")
    absolute_messages: LimitDetail = Field(description="Message count vs absolute limit.")
    absolute_cost: LimitDetail = Field(description="Cost (EUR) vs absolute limit.")

    # Cycle boundaries
    cycle_start: datetime = Field(description="Start of the current billing cycle (UTC).")
    cycle_end: datetime = Field(description="End of the current billing cycle (UTC).")


# ============================================================================
# Admin response schemas
# ============================================================================


class AdminUserUsageLimitResponse(BaseModel):
    """Usage limit data for a single user (admin view).

    Includes user info, configured limits, current usage, and enforcement status.
    """

    model_config = ConfigDict(from_attributes=True)

    # User info
    user_id: UUID = Field(description="User UUID.")
    email: str = Field(description="User email address.")
    full_name: str | None = Field(description="User full name.")
    is_active: bool = Field(description="Whether the user account is active.")

    # Block status
    is_usage_blocked: bool = Field(description="Admin manual kill switch state.")
    blocked_reason: str | None = Field(description="Reason for manual block.")
    blocked_at: datetime | None = Field(description="Timestamp of manual block.")
    blocked_by: UUID | None = Field(description="Admin who set the block.")

    # Configured limits (None = unlimited)
    token_limit_per_cycle: int | None = Field(description="Token limit per cycle.")
    message_limit_per_cycle: int | None = Field(description="Message limit per cycle.")
    cost_limit_per_cycle: Decimal | None = Field(description="Cost limit (EUR) per cycle.")
    token_limit_absolute: int | None = Field(description="Absolute token limit.")
    message_limit_absolute: int | None = Field(description="Absolute message limit.")
    cost_limit_absolute: Decimal | None = Field(description="Absolute cost limit (EUR).")

    # Current usage (from UserStatistics)
    cycle_tokens: int = Field(description="Tokens used in current cycle.")
    cycle_messages: int = Field(description="Messages sent in current cycle.")
    cycle_cost: Decimal = Field(description="Cost (EUR) in current cycle.")
    total_tokens: int = Field(description="Total tokens used (lifetime).")
    total_messages: int = Field(description="Total messages sent (lifetime).")
    total_cost: Decimal = Field(description="Total cost (EUR) (lifetime).")

    # Computed
    status: UsageLimitStatus = Field(description="Overall enforcement status.")
    created_at: datetime = Field(description="User creation timestamp.")


class AdminUserUsageLimitListResponse(BaseModel):
    """Paginated admin list of users with limits and usage."""

    users: list[AdminUserUsageLimitResponse] = Field(description="User limit entries.")
    total: int = Field(description="Total number of matching users.")
    page: int = Field(description="Current page number (1-based).")
    page_size: int = Field(description="Number of items per page.")
    total_pages: int = Field(description="Total number of pages.")


# ============================================================================
# Request schemas
# ============================================================================


class UsageLimitUpdate(BaseModel):
    """Admin update of usage limits for a user.

    All fields are optional — only provided fields are updated.
    None means 'set to unlimited' for that dimension.
    """

    token_limit_per_cycle: int | None = Field(
        default=None,
        ge=0,
        description="Token limit per cycle. None = unlimited.",
    )
    message_limit_per_cycle: int | None = Field(
        default=None,
        ge=0,
        description="Message limit per cycle. None = unlimited.",
    )
    cost_limit_per_cycle: Decimal | None = Field(
        default=None,
        ge=0,
        description="Cost limit (EUR) per cycle. None = unlimited.",
    )
    token_limit_absolute: int | None = Field(
        default=None,
        ge=0,
        description="Absolute token limit. None = unlimited.",
    )
    message_limit_absolute: int | None = Field(
        default=None,
        ge=0,
        description="Absolute message limit. None = unlimited.",
    )
    cost_limit_absolute: Decimal | None = Field(
        default=None,
        ge=0,
        description="Absolute cost limit (EUR). None = unlimited.",
    )


class UsageBlockUpdate(BaseModel):
    """Admin toggle block for a user."""

    is_usage_blocked: bool = Field(description="Whether to block the user.")
    blocked_reason: str | None = Field(
        default=None,
        max_length=USAGE_LIMIT_BLOCKED_REASON_MAX_LENGTH,
        description="Human-readable reason for blocking.",
    )


# ============================================================================
# WebSocket schemas
# ============================================================================


class WebSocketTicketResponse(BaseModel):
    """Response for admin WebSocket ticket creation."""

    ticket: str = Field(description="Single-use WebSocket authentication ticket.")
    ttl_seconds: int = Field(description="Ticket time-to-live in seconds.")
