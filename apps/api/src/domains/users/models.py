"""
Users domain models.
Re-exports User model from auth domain for convenience.
Defines AdminAuditLog for tracking admin actions.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# User model is defined in auth domain
from src.domains.auth.models import User
from src.infrastructure.database.models import UUIDMixin
from src.infrastructure.database.session import Base

__all__ = ["AdminAuditLog", "User"]


class AdminAuditLog(Base, UUIDMixin):
    """
    Audit log for admin actions.
    Tracks all administrative operations for compliance and security.

    Note: This model intentionally does NOT include TimestampMixin (no updated_at).
    Audit logs are immutable by design and should never be modified after creation.
    Only created_at is tracked to record when the action occurred.
    """

    __tablename__ = "admin_audit_log"

    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamp - only created_at (audit logs are immutable)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    # Relationship
    admin_user: Mapped["User"] = relationship()

    def __repr__(self) -> str:
        return f"<AdminAuditLog(action={self.action}, resource={self.resource_type}, admin={self.admin_user_id})>"
