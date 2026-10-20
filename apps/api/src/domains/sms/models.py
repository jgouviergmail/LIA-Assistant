"""Personal message data is encrypted; all equality/search keys are HMACs."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.domains.sms.constants import SMS_SEARCH_INDEX_VERSION
from src.infrastructure.database.models import BaseModel


class SmsMessage(BaseModel):
    __tablename__ = "sms_messages"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    receipt_id: Mapped[UUID] = mapped_column(nullable=False, unique=True)
    sender_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    sender_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    body_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    date_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    proactive_mentioned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    logical_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="UTF-8 content plus binary blind terms; not physical disk size.",
    )
    search_complete: Mapped[bool] = mapped_column(default=True, nullable=False)
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        ForeignKeyConstraint(
            ["user_id", "receipt_id"],
            ["ingestion_receipts.user_id", "ingestion_receipts.id"],
            ondelete="CASCADE",
        ),
        Index("ix_sms_owner_date", "user_id", "received_at", "id"),
        Index(
            "ix_sms_unmentioned",
            "user_id",
            "received_at",
            "id",
            postgresql_where=text("proactive_mentioned_at IS NULL"),
        ),
        Index("ix_sms_owner_sender_date", "user_id", "sender_hash", "received_at", "id"),
    )


class SmsSearchTerm(BaseModel):
    __tablename__ = "sms_search_terms"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[UUID] = mapped_column(nullable=False)
    index_version: Mapped[int] = mapped_column(
        Integer, default=SMS_SEARCH_INDEX_VERSION, server_default=text("1"), nullable=False
    )
    term_hashes: Mapped[list[bytes]] = mapped_column(ARRAY(LargeBinary(32)), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "message_id"],
            ["sms_messages.user_id", "sms_messages.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("message_id", name="uq_sms_index_message"),
        Index("ix_sms_index_owner_message", "user_id", "message_id"),
        Index("ix_sms_terms_gin", "term_hashes", postgresql_using="gin"),
    )


class SmsSenderBlock(BaseModel):
    __tablename__ = "sms_sender_blocks"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    sender_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sender_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "sender_hash", name="uq_sms_owner_sender_block"),)
