"""SMS-owned sender resolutions, encrypted and retained with the SMS archive."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class SmsIdentityState(BaseModel):
    """An account's sender-resolution generation; a reset starts a new one."""

    __tablename__ = "sms_identity_states"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    generation: Mapped[UUID] = mapped_column(default=uuid4, nullable=False)


class SmsSenderIdentity(BaseModel):
    """One sender's encrypted resolution to a contact, under one generation and source."""

    __tablename__ = "sms_sender_identities"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    sender_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[UUID] = mapped_column(nullable=False)
    authority: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("user_id", "sender_hash"),)
