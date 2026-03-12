"""
Pydantic schemas for notifications domain.

Defines request/response models for FCM token management
and admin broadcast messaging.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TokenRegisterRequest(BaseModel):
    """Request to register a new FCM token."""

    token: str = Field(
        ...,
        min_length=10,
        description="Firebase Cloud Messaging token from the client",
    )
    device_type: str = Field(
        ...,
        pattern="^(android|ios|web)$",
        description="Device type: 'android', 'ios', or 'web'",
    )
    device_name: str | None = Field(
        None,
        max_length=100,
        description="Human-readable device name",
    )


class TokenRegisterResponse(BaseModel):
    """Response after registering an FCM token."""

    id: UUID
    device_type: str
    device_name: str | None
    created_at: datetime
    message: str = "Token registered successfully"


class TokenUnregisterRequest(BaseModel):
    """Request to unregister an FCM token."""

    token: str = Field(
        ...,
        min_length=10,
        description="FCM token to unregister",
    )


class TokenUnregisterResponse(BaseModel):
    """Response after unregistering an FCM token."""

    success: bool
    message: str


class UserTokensResponse(BaseModel):
    """Response listing user's registered tokens."""

    tokens: list["TokenInfo"]
    total: int


class TokenInfo(BaseModel):
    """Information about a registered token."""

    id: UUID
    device_type: str
    device_name: str | None
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


# =============================================================================
# Admin Broadcast Schemas
# =============================================================================


class BroadcastMessageRequest(BaseModel):
    """Request to send a broadcast message to users."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="The broadcast message content",
    )
    expires_in_days: int | None = Field(
        None,
        ge=1,
        le=365,
        description="Days until the broadcast expires (null = never)",
    )
    user_ids: list[UUID] | None = Field(
        None,
        description="Optional list of user IDs to send to. If null, sends to all active users.",
    )


class BroadcastMessageResponse(BaseModel):
    """Response after sending a broadcast message."""

    success: bool
    broadcast_id: UUID
    total_users: int
    fcm_sent: int
    fcm_failed: int


class BroadcastInfo(BaseModel):
    """Information about a broadcast message."""

    id: UUID
    message: str
    sent_at: datetime
    sender_name: str | None = None


class UnreadBroadcastsResponse(BaseModel):
    """Response listing unread broadcasts for a user."""

    broadcasts: list[BroadcastInfo]
    total: int


# Rebuild models for forward references
UserTokensResponse.model_rebuild()
