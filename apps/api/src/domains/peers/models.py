"""Peers domain models (peer-connections program, Lot 1).

One row per user pair in ``peer_connections`` (canonical order
``user_a_id < user_b_id`` — the UNIQUE + CHECK constraints make duplicate and
self pairs unrepresentable at the database level). Re-requests after a
decline/removal are STATUS TRANSITIONS on the existing row, never new rows
(spec §5.3). ``peer_access_log`` is immutable (AdminAuditLog pattern):
``created_at`` only, rows are never updated.

Status columns are ``String(20)`` + lowercase ``str``-Enum values (the
open_loops pattern) — a recorded deviation from the spec's
``Enum(native_enum=False)`` that avoids the uppercase-members trap.
"""

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel, UUIDMixin
from src.infrastructure.database.session import Base


class PeerConnectionStatus(str, Enum):
    """Lifecycle of a pair row (single row per pair — transitions only)."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    REMOVED = "removed"


class PeerShareDomain(str, Enum):
    """Shareable domains, v1 set (spec A1). Singular vocabulary."""

    CALENDAR = "calendar"
    TASK = "task"


class PeerShareLevel(str, Enum):
    """Granularity of a share (calendar: availability|details; task: titles)."""

    AVAILABILITY = "availability"
    DETAILS = "details"
    TITLES = "titles"


class PeerMessageStatus(str, Enum):
    """Delivery lifecycle of a relayed message.

    ``delivering`` is the transient claim of the sweep (scheduled_actions
    doctrine): claimed exactly once, recovered back to ``pending`` when a
    crash strands it. String column — adding the value needed no migration.
    """

    PENDING = "pending"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


def canonical_pair(u1: uuid.UUID, u2: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Return the canonical ``(user_a, user_b)`` ordering of a pair.

    Args:
        u1: One side of the pair.
        u2: The other side.

    Returns:
        The two ids ordered so the first is strictly the smaller one.
    """
    return (u1, u2) if u1 < u2 else (u2, u1)


class PeerConnection(BaseModel):
    """One row per user pair; status transitions carry the whole lifecycle."""

    __tablename__ = "peer_connections"

    user_a_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Smaller UUID of the pair (canonical order).",
    )
    user_b_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Larger UUID of the pair (canonical order).",
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Which side initiated the current pending / last request.",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PeerConnectionStatus.PENDING.value,
        server_default=PeerConnectionStatus.PENDING.value,
        index=True,
        comment="pending | accepted | declined | removed (PeerConnectionStatus).",
    )
    context_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Optional requester note, shown provenance-framed to the addressee.",
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="UTC timestamp of the current pending / last request.",
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp of the last accept/decline response.",
    )
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp of the last removal (user action or block).",
    )

    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id", name="uq_peer_connections_pair"),
        CheckConstraint("user_a_id < user_b_id", name="ck_peer_connections_pair_order"),
    )

    def __repr__(self) -> str:
        return (
            f"<PeerConnection(id={self.id}, pair=({self.user_a_id},{self.user_b_id}), "
            f"status={self.status})>"
        )


class PeerBlock(BaseModel):
    """Directional anti-harassment block, independent of any connection row."""

    __tablename__ = "peer_blocks"

    blocker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who placed the block.",
    )
    blocked_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User being blocked (never notified — spec §12.2).",
    )

    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_peer_blocks_pair"),
        CheckConstraint("blocker_id <> blocked_id", name="ck_peer_blocks_not_self"),
    )

    def __repr__(self) -> str:
        return f"<PeerBlock(blocker={self.blocker_id}, blocked={self.blocked_id})>"


class PeerDomainShare(BaseModel):
    """One owner's read-only share of one domain on one connection.

    Absence of a row means NOT shared (default-off, spec requirement). The
    (connection, owner, domain) triple is unique; the level is upserted.
    """

    __tablename__ = "peer_domain_shares"

    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("peer_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Connection this share belongs to.",
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The side of the pair whose data is being shared.",
    )
    domain: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="calendar | task (PeerShareDomain, v1 set — spec A1).",
    )
    level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="availability | details (calendar) or titles (task) — PeerShareLevel.",
    )

    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "owner_user_id",
            "domain",
            name="uq_peer_domain_shares_owner_domain",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PeerDomainShare(connection={self.connection_id}, owner={self.owner_user_id}, "
            f"domain={self.domain}, level={self.level})>"
        )


class PeerMessage(BaseModel):
    """Ledger of one relayed message — and, for a while, of what it said.

    Content is retained on a TTL rather than erased at delivery (ADR-186),
    the exact contract phone calls already use: the ROW survives forever
    (audit, counts, timeline), the TEXT is cleared past ``expires_at`` by the
    peers sweep. Each side keeps only its own words — ``content`` is the
    sender's directive, ``delivered_text`` what the recipient's assistant
    actually said — because showing either across would undo the relay: the
    recipient would read the raw directive instead of their assistant's
    rendering, and the sender would read that assistant's private tone.
    """

    __tablename__ = "peer_messages"

    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("peer_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Connection the message travels on.",
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User whose assistant enqueued the message (pays the LLM cost).",
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User whose assistant delivers the message.",
    )
    content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Sender's own directive text; cleared past expires_at (retention TTL).",
    )
    delivered_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="What the recipient's assistant said; cleared past expires_at.",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC instant past which both texts are purged (row is kept).",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PeerMessageStatus.PENDING.value,
        server_default=PeerMessageStatus.PENDING.value,
        comment="pending | delivering | delivered | failed | cancelled (PeerMessageStatus).",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Real delivery failures so far (deferrals do not count).",
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp of successful delivery.",
    )
    last_error: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Typed error code of the last failure — never raw exception text.",
    )

    __table_args__ = (
        Index("ix_peer_messages_status_created", "status", "created_at"),
        # The retention reaper only ever visits rows that have a horizon.
        Index(
            "ix_peer_messages_expires_at",
            "expires_at",
            postgresql_where=text("expires_at IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PeerMessage(id={self.id}, sender={self.sender_id}, "
            f"recipient={self.recipient_id}, status={self.status})>"
        )


class PeerAccessLog(Base, UUIDMixin):
    """Immutable audit of one cross-user read (AdminAuditLog pattern).

    Read back by the data OWNER in the transparency view (spec §12.4).
    Intentionally no TimestampMixin: audit rows are never updated, only
    ``created_at`` is tracked.
    """

    __tablename__ = "peer_access_log"

    accessor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User whose assistant performed the read.",
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User whose data was read (sees this row in transparency).",
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("peer_connections.id", ondelete="SET NULL"),
        nullable=True,
        comment="Connection the share was checked on (kept if connection dies).",
    )
    domain: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Domain that was read (PeerShareDomain value).",
    )
    tool_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Tool that performed the read (e.g. get_peer_availability).",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    __table_args__ = (Index("ix_peer_access_log_owner_created", "owner_id", "created_at"),)

    def __repr__(self) -> str:
        return (
            f"<PeerAccessLog(accessor={self.accessor_id}, owner={self.owner_id}, "
            f"domain={self.domain})>"
        )


__all__ = [
    "PeerAccessLog",
    "PeerBlock",
    "PeerConnection",
    "PeerConnectionStatus",
    "PeerDomainShare",
    "PeerMessage",
    "PeerMessageStatus",
    "PeerShareDomain",
    "PeerShareLevel",
    "canonical_pair",
]
