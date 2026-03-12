"""
Notifications configuration settings.

Firebase Cloud Messaging (FCM) configuration for push notifications.
Proactive notifications (interests) configuration.
"""

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    INTEREST_NOTIFY_END_HOUR_DEFAULT,
    INTEREST_NOTIFY_START_HOUR_DEFAULT,
    PROACTIVE_FEEDBACK_ENABLED_DEFAULT,
    PROACTIVE_INJECT_LOOKBACK_HOURS_DEFAULT,
    PROACTIVE_INJECT_MAX_MESSAGES_DEFAULT,
    PROACTIVE_NOTIFICATION_MAX_LENGTH_DEFAULT,
)


class NotificationSettings(BaseSettings):
    """
    Configuration for push notifications (Firebase Cloud Messaging).
    Includes proactive notification settings for interests.

    All settings can be overridden via environment variables.
    """

    # Firebase Configuration
    firebase_credentials_path: str = Field(
        default="config/firebase-service-account.json",
        description="Path to Firebase service account JSON file",
    )
    firebase_project_id: str = Field(
        default="",
        description="Firebase project ID",
    )

    # FCM Settings
    fcm_enabled: bool = Field(
        default=True,
        description="Enable/disable FCM notifications globally",
    )
    fcm_default_ttl: int = Field(
        default=86400,
        description="Default TTL for FCM messages in seconds (24 hours)",
    )

    # Token Cleanup
    fcm_token_cleanup_days: int = Field(
        default=30,
        description="Delete inactive tokens older than this many days",
    )

    # ========================================================================
    # Proactive Notifications (Interests)
    # ========================================================================
    proactive_feedback_enabled: bool = Field(
        default=PROACTIVE_FEEDBACK_ENABLED_DEFAULT,
        description="Enable feedback buttons (thumbs up/down/block) on proactive messages",
    )
    interest_notify_start_hour: int = Field(
        default=INTEREST_NOTIFY_START_HOUR_DEFAULT,
        ge=0,
        le=23,
        description="Start hour for proactive notifications (user's local time, 0-23)",
    )
    interest_notify_end_hour: int = Field(
        default=INTEREST_NOTIFY_END_HOUR_DEFAULT,
        ge=0,
        le=23,
        description="End hour for proactive notifications (user's local time, 0-23)",
    )
    # Note: interest_notification_interval_minutes is in AgentsSettings (agents.py)
    proactive_notification_max_length: int = Field(
        default=PROACTIVE_NOTIFICATION_MAX_LENGTH_DEFAULT,
        ge=50,
        le=500,
        description="Max length for push notification preview (characters)",
    )

    # ========================================================================
    # Proactive Message Injection (LangGraph State)
    # ========================================================================
    proactive_inject_max_messages: int = Field(
        default=PROACTIVE_INJECT_MAX_MESSAGES_DEFAULT,
        ge=1,
        le=20,
        description="Max proactive messages to inject into LangGraph state per turn",
    )
    proactive_inject_lookback_hours: int = Field(
        default=PROACTIVE_INJECT_LOOKBACK_HOURS_DEFAULT,
        ge=1,
        le=168,
        description="Lookback window (hours) when no checkpoint exists (new conversation)",
    )
