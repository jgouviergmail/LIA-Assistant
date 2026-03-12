"""
Channel binding Pydantic v2 schemas.

Input/output models for the channels CRUD and OTP API.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.channels.models import ChannelType


class OTPGenerateResponse(BaseModel):
    """Response for OTP code generation."""

    code: str = Field(
        ...,
        description="Generated OTP code to send to the bot",
    )
    expires_in_seconds: int = Field(
        ...,
        description="Seconds until the OTP code expires",
    )
    bot_username: str | None = Field(
        default=None,
        description="Telegram bot @username for user instructions",
    )
    channel_type: ChannelType = Field(
        ...,
        description="Channel type for this OTP",
    )


class ChannelBindingResponse(BaseModel):
    """Response for a single channel binding."""

    id: UUID
    channel_type: ChannelType
    channel_user_id: str
    channel_username: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChannelBindingListResponse(BaseModel):
    """Response for listing channel bindings."""

    bindings: list[ChannelBindingResponse]
    total: int
    telegram_bot_username: str | None = Field(
        default=None,
        description="Telegram bot @username (for UI display before linking)",
    )


class ChannelBindingToggleResponse(BaseModel):
    """Response for toggling a channel binding."""

    id: UUID
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
