"""Durable spend fences, deliberately separate from ephemeral human text."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class WorldMessageAttempt(BaseModel):
    __tablename__ = "world_message_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('reserved','queued','running','delivered','succeeded','failed','uncertain')",
            name="ck_world_message_attempt_status",
        ),
        Index("ix_world_message_attempt_queue", "namespace", "status", "created_at", "id"),
        Index("ix_world_message_attempt_expiry", "expires_at"),
    )

    namespace: Mapped[str] = mapped_column(String(40), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipient_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    token: Mapped[UUID] = mapped_column(default=uuid4, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    content_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    queued_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    running_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
