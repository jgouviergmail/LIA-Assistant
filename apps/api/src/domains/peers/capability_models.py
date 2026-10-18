"""Durable peer transfer receipts and independently committed component identities."""

from datetime import datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class PeerCapabilityTransfer(BaseModel):
    __tablename__ = "peer_capability_transfers"

    sender_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    recipient_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    connection_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("peer_connections.id", ondelete="SET NULL")
    )
    source_id: Mapped[UUID] = mapped_column(nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    digest: Mapped[str] = mapped_column(String(64))
    payload_bytes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    snapshot: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="preparing", server_default="preparing")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    transferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[UUID | None] = mapped_column(nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fence: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64))
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    __table_args__ = (
        UniqueConstraint(
            "sender_id", "idempotency_key", name="uq_peer_capability_transfer_request"
        ),
        CheckConstraint(
            "kind IN ('skill','mcp','plugin')", name="ck_peer_capability_transfer_kind"
        ),
        CheckConstraint(
            "status IN ('preparing','installing','installed','partial','failed','cancelled')",
            name="ck_peer_capability_transfer_status",
        ),
        CheckConstraint(
            "sender_id IS NULL OR sender_id <> recipient_id",
            name="ck_peer_capability_transfer_distinct_users",
        ),
    )


class PeerCapabilityComponent(BaseModel):
    __tablename__ = "peer_capability_components"

    transfer_id: Mapped[UUID] = mapped_column(
        ForeignKey("peer_capability_transfers.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    key: Mapped[str] = mapped_column(String(180))
    resource_id: Mapped[UUID | None] = mapped_column(nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    installed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    error_code: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint(
            "transfer_id", "kind", "key", name="uq_peer_capability_component_identity"
        ),
        UniqueConstraint("kind", "resource_id", name="uq_peer_capability_component_resource"),
        CheckConstraint(
            "kind IN ('skill','mcp','plugin')", name="ck_peer_capability_component_kind"
        ),
    )
