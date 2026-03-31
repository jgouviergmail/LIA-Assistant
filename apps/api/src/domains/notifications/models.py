"""
Notifications domain models (database entities).

Manages FCM (Firebase Cloud Messaging) tokens for push notifications
and admin broadcast messages.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.auth.models import User


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
    user: Mapped["User"] = relationship(back_populates="fcm_tokens")

    def __repr__(self) -> str:
        return (
            f"<UserFCMToken(id={self.id}, user_id={self.user_id}, device_type={self.device_type})>"
        )


class AdminBroadcast(BaseModel):
    """
    Broadcast message sent by admin to all active users.

    Used for important announcements that all users must see.
    Tracks delivery stats (FCM sent/failed) and links to read receipts.
    """

    __tablename__ = "admin_broadcasts"

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The broadcast message content",
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
    sender: Mapped["User"] = relationship("User", foreign_keys=[sent_by])
    reads: Mapped[list["UserBroadcastRead"]] = relationship(
        back_populates="broadcast",
        cascade="all, delete-orphan",
    )

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
    user: Mapped["User"] = relationship("User")
    broadcast: Mapped["AdminBroadcast"] = relationship(back_populates="reads")

    def __repr__(self) -> str:
        return f"<UserBroadcastRead(user_id={self.user_id}, broadcast_id={self.broadcast_id})>"
