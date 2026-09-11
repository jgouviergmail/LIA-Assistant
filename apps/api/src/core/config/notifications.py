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
    MOMENTS_BUSY_GUARD_CACHE_SECONDS_DEFAULT,
    MOMENTS_BUSY_GUARD_WINDOW_HOURS_DEFAULT,
    MOMENTS_CLAIM_LEASE_MINUTES_DEFAULT,
    MOMENTS_DETECT_LOOKBACK_MINUTES_DEFAULT,
    MOMENTS_EVENT_CHAIN_GAP_MINUTES_DEFAULT,
    MOMENTS_EVENT_FOLLOWUP_DELAY_MINUTES_DEFAULT,
    MOMENTS_EVENT_FOLLOWUP_MIN_SCORE_DEFAULT,
    MOMENTS_EVENT_FOLLOWUP_WINDOW_MINUTES_DEFAULT,
    MOMENTS_EVENT_MIN_DURATION_MINUTES_DEFAULT,
    MOMENTS_RETENTION_DAYS_DEFAULT,
    MOMENTS_SWEEP_BATCH_SIZE_DEFAULT,
    MOMENTS_SWEEP_INTERVAL_MINUTES_DEFAULT,
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
        default="compagnonnotif",
        description="Firebase project ID",
    )

    # ------------------------------------------------------------------
    # Firebase CLIENT options, published to the native Android shell
    # ------------------------------------------------------------------
    # These are not secrets: every Android build ships them inside its APK.
    # They live here so one published app can talk to whichever Firebase
    # project its server owns, initialising Firebase at runtime instead of
    # baking a google-services.json into the binary. Unset means the Android
    # shell receives no notifications from this deployment.
    firebase_android_app_id: str | None = Field(
        default=None,
        description=(
            "mobilesdk_app_id of the Android app in this deployment's Firebase "
            "project (NOT the package name)."
        ),
    )
    firebase_api_key: str | None = Field(
        default=None,
        description=(
            "API key of the ANDROID client in this deployment's Firebase project "
            "(api_key.current_key in google-services.json). Often the same string "
            "as the web key, but not always: a web key restricted by HTTP referrer "
            "is rejected from a device, which reads as 'push does not work'."
        ),
    )
    firebase_sender_id: str | None = Field(
        default=None,
        description="Cloud Messaging sender id of this deployment's Firebase project.",
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

    # ========================================================================
    # Anticipated moments — LIA comes back at an INSTANT, not at a tick
    # ========================================================================
    moments_enabled: bool = Field(
        default=False,
        description=(
            "Deployment ceiling for anticipated moments (PlatformCapability.MOMENTS). "
            "Off by default: it adds a scheduler job and a way to be interrupted."
        ),
    )
    moments_sweep_interval_minutes: int = Field(
        default=MOMENTS_SWEEP_INTERVAL_MINUTES_DEFAULT,
        ge=1,
        le=60,
        description="Interval between moment sweeps (minutes). Jittered (ADR-254).",
    )
    moments_sweep_batch_size: int = Field(
        default=MOMENTS_SWEEP_BATCH_SIZE_DEFAULT,
        ge=1,
        le=200,
        description="Accounts examined per moment sweep.",
    )
    moments_claim_lease_minutes: int = Field(
        default=MOMENTS_CLAIM_LEASE_MINUTES_DEFAULT,
        ge=2,
        le=240,
        description=(
            "How long a claimed moment may go unsettled before the sweep gives "
            "it back. Generous on purpose: a lease shorter than a real serve "
            "would hand the same moment to a second worker mid-sentence."
        ),
    )
    moments_retention_days: int = Field(
        default=MOMENTS_RETENTION_DAYS_DEFAULT,
        ge=1,
        le=365,
        description=(
            "Days a settled moment row is kept before purge. Not a register: the "
            "durable trace is agent_effects and heartbeat_notifications."
        ),
    )
    moments_detect_lookback_minutes: int = Field(
        default=MOMENTS_DETECT_LOOKBACK_MINUTES_DEFAULT,
        ge=30,
        le=1440,
        description=(
            "How far back the calendar detector reads. Must exceed the follow-up "
            "window, or an event would stop being visible before its moment is due."
        ),
    )
    moments_event_followup_delay_minutes: int = Field(
        default=MOMENTS_EVENT_FOLLOWUP_DELAY_MINUTES_DEFAULT,
        ge=1,
        le=180,
        description="Minutes after an event ends before its follow-up falls due.",
    )
    moments_event_followup_window_minutes: int = Field(
        default=MOMENTS_EVENT_FOLLOWUP_WINDOW_MINUTES_DEFAULT,
        ge=15,
        le=720,
        description="How long a follow-up stays worth serving once due.",
    )
    moments_event_min_duration_minutes: int = Field(
        default=MOMENTS_EVENT_MIN_DURATION_MINUTES_DEFAULT,
        ge=5,
        le=240,
        description="Shortest event that can earn a follow-up.",
    )
    moments_event_followup_min_score: int = Field(
        default=MOMENTS_EVENT_FOLLOWUP_MIN_SCORE_DEFAULT,
        ge=1,
        le=5,
        description="Importance points an event must reach to earn a follow-up.",
    )
    moments_event_chain_gap_minutes: int = Field(
        default=MOMENTS_EVENT_CHAIN_GAP_MINUTES_DEFAULT,
        ge=0,
        le=120,
        description=("Two events closer than this are one block: only the last earns a " "moment."),
    )

    # Do not interrupt someone who is in a meeting. ON by default: this is a
    # reduction of noise in a capability that already exists, not a new one.
    moments_busy_guard_enabled: bool = Field(
        default=True,
        description=(
            "Skip a heartbeat tick while a meeting the person attends is in "
            "progress. A moment is never deferred by it."
        ),
    )
    moments_busy_guard_window_hours: int = Field(
        default=MOMENTS_BUSY_GUARD_WINDOW_HOURS_DEFAULT,
        ge=1,
        le=12,
        description="Hours read either side of now to find a meeting in progress.",
    )
    moments_busy_guard_cache_seconds: int = Field(
        default=MOMENTS_BUSY_GUARD_CACHE_SECONDS_DEFAULT,
        ge=60,
        le=3600,
        description="How long a busy verdict is trusted before the calendar is re-read.",
    )
