"""Durable sources, scoped credentials, opaque receipts and delivery leases."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class IngestionSource(BaseModel):
    __tablename__ = "ingestion_sources"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    resource: Mapped[str] = mapped_column(String(32), nullable=False)
    label_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        Index("ix_ingestion_sources_owner", "user_id", "resource"),
    )


class IngestionToken(BaseModel):
    __tablename__ = "ingestion_tokens"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[UUID] = mapped_column(nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(48)), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "source_id"],
            ["ingestion_sources.user_id", "ingestion_sources.id"],
            ondelete="CASCADE",
        ),
    )


class IngestionReceipt(BaseModel):
    __tablename__ = "ingestion_receipts"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[UUID] = mapped_column(nullable=False)
    event_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    filter_version: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("source_id", "event_key", name="uq_ingestion_receipt_source_event"),
        ForeignKeyConstraint(
            ["user_id", "source_id"],
            ["ingestion_sources.user_id", "ingestion_sources.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "verdict IN ('stored','ignored_sensitive','ignored_sender','deleted')",
            name="ck_ingestion_receipt_verdict",
        ),
    )


class IngestionDelivery(BaseModel):
    __tablename__ = "ingestion_deliveries"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    receipt_id: Mapped[UUID] = mapped_column(nullable=False)
    destination_key: Mapped[str] = mapped_column(String(64), default="fanout", nullable=False)
    device_id: Mapped[UUID | None] = mapped_column()
    state: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fence: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    lease_owner: Mapped[UUID | None] = mapped_column()
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effect_id: Mapped[UUID | None] = mapped_column()
    last_error_code: Mapped[str | None] = mapped_column(String(48))
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "receipt_id"],
            ["ingestion_receipts.user_id", "ingestion_receipts.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("receipt_id", "destination_key", name="uq_ingestion_delivery_destination"),
        CheckConstraint(
            "state IN ('pending','sending','sent','failed','unknown','cancelled','expanded')",
            name="ck_ingestion_delivery_state",
        ),
        Index("ix_ingestion_delivery_claim", "state", "next_attempt_at"),
    )
