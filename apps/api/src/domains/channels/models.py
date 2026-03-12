"""
Channel binding domain models.

Stores per-user external messaging channel bindings (Telegram, etc.).
Each user can link one account per channel type. The model is generic
to support future channels (Discord, WhatsApp) with minimal changes.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class ChannelType(StrEnum):
    """Supported messaging channel types."""

    TELEGRAM = "telegram"


class UserChannelBinding(BaseModel):
    """
    Per-user external channel binding.

    Links a LIA user account to an external messaging platform
    account (e.g., Telegram chat_id). The binding is established via
    an OTP verification flow and enables bidirectional messaging.

    Constraints:
    - One binding per (user, channel_type) — a user can only link one Telegram account
    - One binding per (channel_type, channel_user_id) — a Telegram account can only be
      linked to one LIA user
    - Partial index on active bindings for fast webhook lookup (hot path)
    """

    __tablename__ = "user_channel_bindings"

    # Foreign key to user
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Channel identity
    channel_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Channel type discriminant (e.g., 'telegram')",
    )

    channel_user_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Provider-specific user identifier (e.g., Telegram chat_id)",
    )

    channel_username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Provider-specific display name (e.g., Telegram @username)",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        doc="Whether this binding is active (can be toggled by user)",
    )

    # NOTE: No ORM relationship to User — user_id FK is sufficient.
    # Same pattern as UserMCPServer: avoids fragile import-order dependencies.

    __table_args__ = (
        # One binding per user per channel type
        UniqueConstraint("user_id", "channel_type", name="uq_user_channel_binding_type"),
        # One user per channel account
        UniqueConstraint("channel_type", "channel_user_id", name="uq_channel_type_user_id"),
        # Hot path: webhook lookup by (channel_type, channel_user_id) for active bindings
        Index(
            "ix_channel_bindings_active_lookup",
            "channel_type",
            "channel_user_id",
            postgresql_where="is_active = true",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<UserChannelBinding(id={self.id}, channel_type='{self.channel_type}', "
            f"channel_user_id='{self.channel_user_id}', is_active={self.is_active})>"
        )
