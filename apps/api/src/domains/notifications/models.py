"""
Notifications domain models (database entities).

Manages FCM (Firebase Cloud Messaging) tokens for push notifications
and admin broadcast messages.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.users.models import User


class UserFCMToken(BaseModel):
    """
    FCM token for push notifications.

    Each user can have multiple tokens (one per device).
    Tokens are used by Firebase Cloud Messaging to send push notifications.
    """

    __tablename__ = "user_fcm_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of the FCM token",
    )

    # FCM Token (can be very long)
    token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
        comment="Firebase Cloud Messaging token",
    )

    # Device information
    device_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Device type: 'android', 'ios', 'web'",
    )
    device_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Human-readable device name (e.g., 'iPhone de Jean')",
    )

    # Token status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether the token is active (False if FCM reports invalid)",
    )

    # Usage tracking
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time a notification was sent to this token",
    )

    # Error tracking for invalid tokens
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Last FCM error for this token (for debugging)",
    )

    # Relationship
    user: Mapped[User] = relationship(back_populates="fcm_tokens")

    def __repr__(self) -> str:
        return (
            f"<UserFCMToken(id={self.id}, user_id={self.user_id}, device_type={self.device_type})>"
        )


class BroadcastAudience(str, Enum):
    """Who a broadcast is addressed to (ADR-312).

    A ``str`` enum stored as its lowercase value in a ``String(20)`` column (the
    peers pattern), so a raw string read back compares equal to a member.
    """

    #: Every active account at send time.
    ALL = "all"
    #: The accounts listed in ``admin_broadcast_recipients``, and nobody else.
    SELECTED = "selected"


class AdminBroadcast(BaseModel):
    """
    Broadcast message sent by an admin to all active users or to a selection.

    Used for important announcements. Tracks delivery stats (FCM sent/failed),
    links to read receipts, and — since ADR-312 — says who it was addressed to:
    a targeted broadcast used to be stored without its recipients, and the
    unread listing then served it to every account at its next sign-in.
    """

    __tablename__ = "admin_broadcasts"

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The broadcast message content",
    )

    audience: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=BroadcastAudience.ALL.value,
        server_default=BroadcastAudience.ALL.value,
        comment=(
            "Who the broadcast is addressed to: all (every active account at send "
            "time) | selected (the admin_broadcast_recipients rows) — ADR-312."
        ),
    )

    sent_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Admin user who sent the broadcast (NULL if admin account was hard-deleted)",
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the broadcast expires (null = never)",
    )

    message_translations: Mapped[dict[str, str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Cached translations {language: text}. Filled at send time, "
            "lazily backfilled on read for historical broadcasts — reading "
            "an already-translated broadcast costs 0 LLM calls (N-213.2)"
        ),
    )

    # Delivery stats
    total_recipients: Mapped[int] = mapped_column(
        default=0,
        comment="Total number of active users at send time",
    )
    fcm_sent: Mapped[int] = mapped_column(
        default=0,
        comment="Number of FCM notifications successfully sent",
    )
    fcm_failed: Mapped[int] = mapped_column(
        default=0,
        comment="Number of FCM notifications that failed",
    )

    # Relationships
    sender: Mapped[User] = relationship("User", foreign_keys=[sent_by])
    reads: Mapped[list[UserBroadcastRead]] = relationship(
        back_populates="broadcast",
        cascade="all, delete-orphan",
    )

    # Recent-broadcasts listing (ordered by created_at).
    __table_args__ = (Index("ix_admin_broadcasts_created_at", "created_at"),)

    def __repr__(self) -> str:
        return (
            f"<AdminBroadcast(id={self.id}, sent_by={self.sent_by}, created_at={self.created_at})>"
        )


class UserBroadcastRead(BaseModel):
    """
    Tracks which users have read which broadcasts.

    Used to ensure every user sees every broadcast message,
    even if they were offline when it was sent.
    """

    __tablename__ = "user_broadcast_reads"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User who read the broadcast",
    )

    broadcast_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_broadcasts.id", ondelete="CASCADE"),
        nullable=False,
        comment="Broadcast that was read",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "broadcast_id", name="uq_user_broadcast_read"),
        Index("ix_user_broadcast_reads_user_id", "user_id"),
    )

    # Relationships
    user: Mapped[User] = relationship("User")
    broadcast: Mapped[AdminBroadcast] = relationship(back_populates="reads")

    def __repr__(self) -> str:
        return f"<UserBroadcastRead(user_id={self.user_id}, broadcast_id={self.broadcast_id})>"


class AdminBroadcastRecipient(BaseModel):
    """One account a SELECTED broadcast is addressed to (ADR-312).

    Written in the transaction that creates the broadcast, from the accounts the
    send actually resolved (active ones). Read by the unread listing — a
    broadcast addressed to others is neither served nor counted in a reader's
    window — and by the admin history, which names a sample of them.
    """

    __tablename__ = "admin_broadcast_recipients"

    broadcast_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_broadcasts.id", ondelete="CASCADE"),
        nullable=False,
        comment="The selected-audience broadcast",
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="An account the broadcast is addressed to",
    )

    __table_args__ = (
        UniqueConstraint("broadcast_id", "user_id", name="uq_admin_broadcast_recipients"),
        # The unread listing probes « is this reader a recipient » per broadcast.
        Index("ix_admin_broadcast_recipients_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AdminBroadcastRecipient(broadcast_id={self.broadcast_id}, user_id={self.user_id})>"
        )
