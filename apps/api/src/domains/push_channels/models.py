"""Push channel registry model (lot H, 2026-08).

One row per live Google watch: who it belongs to, which provider surface it
watches, the secrets Google echoes back, and when it expires (the renewal
job re-creates channels before expiry).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class PushChannelProvider(str, Enum):
    """Which Google surface a channel watches."""

    GOOGLE_CALENDAR = "google_calendar"  # events.watch on the primary calendar
    GOOGLE_DRIVE = "google_drive"  # changes.watch on the whole Drive
    GOOGLE_GMAIL = "google_gmail"  # users.watch via Pub/Sub (phase 2)


class WebhookChannel(BaseModel):
    """A live Google push channel (or Gmail watch) owned by one user."""

    __tablename__ = "webhook_channels"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "watch_target", name="uq_webhook_channel_target"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="google_calendar | google_drive | google_gmail",
    )
    watch_target: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="calendar id, 'changes' (drive) or the mailbox address (gmail)",
    )
    channel_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="Our channel identifier, echoed by Google in X-Goog-Channel-ID",
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Google's opaque resource id (needed to stop the channel)",
    )
    token: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Opaque secret echoed by Google in X-Goog-Channel-Token",
    )
    expiration: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Channel expiry (UTC) — renewal recreates before this instant",
    )
    page_token: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Drive only: the changes baseline pageToken of the watch",
    )
    last_history_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Gmail only: highest historyId seen (Pub/Sub dedup ledger)",
    )
    last_notification_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last accepted notification (freshness/monitoring signal)",
    )
