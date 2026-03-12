"""
Channels configuration module.

Contains settings for:
- Channels feature toggle (enabled/disabled)
- Telegram bot configuration (token, webhook, bot username)
- OTP linking flow (TTL, length, brute-force protection)
- Rate limiting (per-user, global)
- Message processing (lock TTL, max message length)

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
Reference: docs/technical/CHANNELS_INTEGRATION.md
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    CHANNEL_MESSAGE_LOCK_TTL_SECONDS_DEFAULT,
    CHANNEL_OTP_BLOCK_TTL_SECONDS_DEFAULT,
    CHANNEL_OTP_LENGTH_DEFAULT,
    CHANNEL_OTP_MAX_ATTEMPTS_DEFAULT,
    CHANNEL_OTP_TTL_SECONDS_DEFAULT,
    CHANNEL_RATE_LIMIT_GLOBAL_PER_SECOND_DEFAULT,
    CHANNEL_RATE_LIMIT_PER_USER_PER_MINUTE_DEFAULT,
    TELEGRAM_MESSAGE_MAX_LENGTH_DEFAULT,
)


class ChannelsSettings(BaseSettings):
    """Channels settings for external messaging platforms (Telegram, etc.)."""

    # ========================================================================
    # Feature Toggle
    # ========================================================================

    channels_enabled: bool = Field(
        default=False,
        description=(
            "Enable multi-channel messaging support. When true, users can "
            "link external messaging accounts (Telegram, etc.) and chat with LIA."
        ),
    )

    # ========================================================================
    # Telegram Bot Configuration
    # ========================================================================

    telegram_bot_token: str | None = Field(
        default=None,
        repr=False,
        description="Telegram Bot API token from @BotFather.",
    )

    telegram_webhook_secret: str | None = Field(
        default=None,
        repr=False,
        description=(
            "Secret token for Telegram webhook signature verification "
            "(X-Telegram-Bot-Api-Secret-Token header)."
        ),
    )

    telegram_webhook_url: str | None = Field(
        default=None,
        description=(
            "Public HTTPS URL for Telegram webhook (production). "
            "If absent, long polling is used (development)."
        ),
    )

    telegram_bot_username: str | None = Field(
        default=None,
        description=(
            "Deprecated — auto-discovered via getMe at startup (see bot.py "
            "get_bot_username()). This setting is kept for backward compatibility "
            "but is no longer read by the application."
        ),
    )

    telegram_message_max_length: int = Field(
        default=TELEGRAM_MESSAGE_MAX_LENGTH_DEFAULT,
        ge=100,
        le=4096,
        description="Maximum characters per Telegram message before splitting.",
    )

    # ========================================================================
    # OTP Linking Flow
    # ========================================================================

    channel_otp_ttl_seconds: int = Field(
        default=CHANNEL_OTP_TTL_SECONDS_DEFAULT,
        ge=60,
        le=900,
        description="TTL for OTP codes in Redis (seconds).",
    )

    channel_otp_length: int = Field(
        default=CHANNEL_OTP_LENGTH_DEFAULT,
        ge=4,
        le=8,
        description="Length of generated OTP codes (digits).",
    )

    channel_otp_max_attempts: int = Field(
        default=CHANNEL_OTP_MAX_ATTEMPTS_DEFAULT,
        ge=3,
        le=20,
        description="Max OTP verification attempts per chat_id before blocking.",
    )

    channel_otp_block_ttl_seconds: int = Field(
        default=CHANNEL_OTP_BLOCK_TTL_SECONDS_DEFAULT,
        ge=300,
        le=3600,
        description="Duration of OTP brute-force block per chat_id (seconds).",
    )

    # ========================================================================
    # Rate Limiting
    # ========================================================================

    channel_rate_limit_per_user_per_minute: int = Field(
        default=CHANNEL_RATE_LIMIT_PER_USER_PER_MINUTE_DEFAULT,
        ge=1,
        le=60,
        description="Max inbound messages per user per minute.",
    )

    channel_rate_limit_global_per_second: int = Field(
        default=CHANNEL_RATE_LIMIT_GLOBAL_PER_SECOND_DEFAULT,
        ge=5,
        le=100,
        description="Max global inbound messages per second (across all users).",
    )

    # ========================================================================
    # Message Processing
    # ========================================================================

    channel_message_lock_ttl_seconds: int = Field(
        default=CHANNEL_MESSAGE_LOCK_TTL_SECONDS_DEFAULT,
        ge=30,
        le=300,
        description="Redis lock TTL per-user for sequential message processing (seconds).",
    )
