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
