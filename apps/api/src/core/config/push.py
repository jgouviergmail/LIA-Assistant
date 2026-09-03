"""Google push channels settings (lot H, 2026-08).

Composed into the main ``Settings`` class. Phase flags default OFF: polling
remains the behavior until the platform prerequisites are met (phase 1:
domain ownership verified for the webhook URL; phase 2: Pub/Sub topic +
publish grant to Gmail's service account).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.constants import (
    PUSH_NOTIFICATION_DEBOUNCE_SECONDS_DEFAULT,
    PUSH_RENEWAL_MARGIN_SECONDS_DEFAULT,
    PUSH_SYNC_INTERVAL_MINUTES_DEFAULT,
    PUSH_WAKE_CALENDAR_LOOKAHEAD_HOURS_DEFAULT,
    PUSH_WAKE_CALENDAR_RECENT_UPDATE_MINUTES_DEFAULT,
    PUSH_WAKE_COOLDOWN_MINUTES_DEFAULT,
    PUSH_WAKE_MAIL_EXCLUDE_LABELS_DEFAULT,
    PUSH_WAKE_MAIL_REQUIRE_LABELS_DEFAULT,
    PUSH_WAKE_MAX_USERS_PER_SWEEP_DEFAULT,
    PUSH_WAKE_PAYLOAD_TTL_SECONDS_DEFAULT,
    PUSH_WAKE_SWEEP_INTERVAL_SECONDS_DEFAULT,
    PUSH_WATCH_TTL_SECONDS_DEFAULT,
)


class PushSettings(BaseSettings):
    """Google push channel settings (phase flags + tunables)."""

    model_config = SettingsConfigDict(extra="ignore")

    push_channels_enabled: bool = Field(
        default=False,
        description=(
            "Phase 1 master switch: Calendar events.watch + Drive changes.watch "
            "channels. Requires push_webhook_url on an ownership-verified domain."
        ),
    )
    gmail_push_enabled: bool = Field(
        default=False,
        description=(
            "Phase 2 switch: Gmail users.watch through Pub/Sub. Requires "
            "gmail_pubsub_topic and gmail_pubsub_push_token (the push "
            "subscription must append ?token=<value> to the webhook URL)."
        ),
    )
    push_webhook_url: str | None = Field(
        default=None,
        description=(
            "Public HTTPS URL of the Google webhook endpoint "
            "(e.g. https://api.example.com/api/v1/webhooks/google). The domain "
            "must be ownership-verified in Search Console and registered in the "
            "GCP project's allowed push domains."
        ),
    )
    gmail_pubsub_topic: str | None = Field(
        default=None,
        description=(
            "Full Pub/Sub topic for Gmail push "
            "(projects/{project}/topics/{topic}). Phase 2 only."
        ),
    )
    gmail_pubsub_push_token: str | None = Field(
        default=None,
        repr=False,
        description=(
            "Shared secret carried by the Pub/Sub push subscription as a "
            "?token= query parameter — the gate distinguishing Google's "
            "deliveries from anyone who found the public URL. Phase 2 only."
        ),
    )
    push_watch_ttl_seconds: int = Field(
        default=PUSH_WATCH_TTL_SECONDS_DEFAULT,
        description="Requested channel lifetime (Google may shorten it).",
    )
    push_renewal_margin_seconds: int = Field(
        default=PUSH_RENEWAL_MARGIN_SECONDS_DEFAULT,
        description="Channels expiring within this margin get renewed.",
    )
    push_sync_interval_minutes: int = Field(
        default=PUSH_SYNC_INTERVAL_MINUTES_DEFAULT,
        description="Interval of the leader-elected channel sync job.",
    )
    push_notification_debounce_seconds: int = Field(
        default=PUSH_NOTIFICATION_DEBOUNCE_SECONDS_DEFAULT,
        description="Per-channel debounce window against notification storms.",
    )
    # --- Push-driven heartbeat wake (ADR-261) ---------------------------------
    push_wake_enabled: bool = Field(
        default=False,
        description="A processed push notification queues the user for an event-driven "
        "heartbeat decision (served by a short sweep under the full eligibility "
        "checker). Requires push_channels_enabled and heartbeat_enabled.",
    )
    push_wake_sweep_interval_seconds: int = Field(
        default=PUSH_WAKE_SWEEP_INTERVAL_SECONDS_DEFAULT,
        ge=30,
        le=900,
        description="Interval of the leader-elected wake sweep (jittered).",
    )
    push_wake_cooldown_minutes: int = Field(
        default=PUSH_WAKE_COOLDOWN_MINUTES_DEFAULT,
        ge=1,
        le=240,
        description="Minimum minutes between two served wakes for one user (on top of "
        "the heartbeat's own cooldowns).",
    )
    push_wake_max_users_per_sweep: int = Field(
        default=PUSH_WAKE_MAX_USERS_PER_SWEEP_DEFAULT,
        ge=1,
        le=100,
        description="Users served per sweep; the rest wait for the next one.",
    )
    push_wake_payload_ttl_seconds: int = Field(
        default=PUSH_WAKE_PAYLOAD_TTL_SECONDS_DEFAULT,
        ge=60,
        le=86400,
        description="How long a queued wake stays valid before it is dropped as stale.",
    )
    push_wake_mail_require_labels: list[str] = Field(
        default=list(PUSH_WAKE_MAIL_REQUIRE_LABELS_DEFAULT),
        description="A new mail wakes the heartbeat only when it carries one of these "
        "Gmail labels (Google's own importance classifier by default).",
    )
    push_wake_mail_exclude_labels: list[str] = Field(
        default=list(PUSH_WAKE_MAIL_EXCLUDE_LABELS_DEFAULT),
        description="Gmail labels that never wake (promotions, social, forums).",
    )
    push_wake_mail_exclude_list_mail: bool = Field(
        default=True,
        description="Mail carrying List-Unsubscribe or a bulk/list Precedence never wakes.",
    )
    push_wake_calendar_lookahead_hours: int = Field(
        default=PUSH_WAKE_CALENDAR_LOOKAHEAD_HOURS_DEFAULT,
        ge=1,
        le=168,
        description="A calendar change wakes only for an event starting within this horizon.",
    )
    push_wake_calendar_recent_update_minutes: int = Field(
        default=PUSH_WAKE_CALENDAR_RECENT_UPDATE_MINUTES_DEFAULT,
        ge=1,
        le=120,
        description="A calendar change wakes only when the event was updated this recently "
        "(the notification itself is the clock; older edits are the tick's business).",
    )
