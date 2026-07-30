"""add peers tables

Peer-connections program, Lot 1 (spec:
docs/superpowers/specs/2026-07-29-peer-connections-design.md). One row per
user pair in peer_connections (UNIQUE + CHECK make duplicate/self pairs
unrepresentable); peer_blocks is directional and independent; shares are
default-off (absence = not shared); peer_messages is the delivery ledger
(content scrubbed post-delivery); peer_access_log is immutable audit.
Also adds the users.discovery_enabled opt-in column (default false).

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-29 09:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the 5 peers tables + the users.discovery_enabled opt-in column."""
    op.add_column(
        "users",
        sa.Column(
            "discovery_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Opt-in: this user can be found by peer discovery search. Default off.",
        ),
    )

    op.create_table(
        "peer_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_a_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="Smaller UUID of the pair (canonical order).",
        ),
        sa.Column(
            "user_b_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="Larger UUID of the pair (canonical order).",
        ),
        sa.Column(
            "requested_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="Which side initiated the current pending / last request.",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
            comment="pending | accepted | declined | removed (PeerConnectionStatus).",
        ),
        sa.Column(
            "context_message",
            sa.String(length=500),
            nullable=True,
            comment="Optional requester note, shown provenance-framed to the addressee.",
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC timestamp of the current pending / last request.",
        ),
        sa.Column(
            "responded_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC timestamp of the last accept/decline response.",
        ),
        sa.Column(
            "removed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC timestamp of the last removal (user action or block).",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_a_id", "user_b_id", name="uq_peer_connections_pair"),
        sa.CheckConstraint("user_a_id < user_b_id", name="ck_peer_connections_pair_order"),
    )
    op.create_index("ix_peer_connections_user_a_id", "peer_connections", ["user_a_id"])
    op.create_index("ix_peer_connections_user_b_id", "peer_connections", ["user_b_id"])
    op.create_index("ix_peer_connections_status", "peer_connections", ["status"])

    op.create_table(
        "peer_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "blocker_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="User who placed the block.",
        ),
        sa.Column(
            "blocked_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="User being blocked (never notified — spec §12.2).",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_peer_blocks_pair"),
        sa.CheckConstraint("blocker_id <> blocked_id", name="ck_peer_blocks_not_self"),
    )
    op.create_index("ix_peer_blocks_blocker_id", "peer_blocks", ["blocker_id"])
    op.create_index("ix_peer_blocks_blocked_id", "peer_blocks", ["blocked_id"])

    op.create_table(
        "peer_domain_shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("peer_connections.id", ondelete="CASCADE"),
            nullable=False,
            comment="Connection this share belongs to.",
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="The side of the pair whose data is being shared.",
        ),
        sa.Column(
            "domain",
            sa.String(length=20),
            nullable=False,
            comment="calendar | task (PeerShareDomain, v1 set — spec A1).",
        ),
        sa.Column(
            "level",
            sa.String(length=20),
            nullable=False,
            comment="availability | details (calendar) or titles (task) — PeerShareLevel.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "connection_id",
            "owner_user_id",
            "domain",
            name="uq_peer_domain_shares_owner_domain",
        ),
    )
    op.create_index("ix_peer_domain_shares_connection_id", "peer_domain_shares", ["connection_id"])
    op.create_index("ix_peer_domain_shares_owner_user_id", "peer_domain_shares", ["owner_user_id"])

    op.create_table(
        "peer_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("peer_connections.id", ondelete="CASCADE"),
            nullable=False,
            comment="Connection the message travels on.",
        ),
        sa.Column(
            "sender_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="User whose assistant enqueued the message (pays the LLM cost).",
        ),
        sa.Column(
            "recipient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="User whose assistant delivers the message.",
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=True,
            comment="Sender directive text; set to NULL after successful delivery.",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
            comment="pending | delivering | delivered | failed | cancelled (PeerMessageStatus).",
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Real delivery failures so far (deferrals do not count).",
        ),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC timestamp of successful delivery.",
        ),
        sa.Column(
            "last_error",
            sa.String(length=50),
            nullable=True,
            comment="Typed error code of the last failure — never raw exception text.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_peer_messages_connection_id", "peer_messages", ["connection_id"])
    op.create_index("ix_peer_messages_sender_id", "peer_messages", ["sender_id"])
    op.create_index("ix_peer_messages_recipient_id", "peer_messages", ["recipient_id"])
    op.create_index("ix_peer_messages_status_created", "peer_messages", ["status", "created_at"])

    op.create_table(
        "peer_access_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "accessor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="User whose assistant performed the read.",
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="User whose data was read (sees this row in transparency).",
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("peer_connections.id", ondelete="SET NULL"),
            nullable=True,
            comment="Connection the share was checked on (kept if connection dies).",
        ),
        sa.Column(
            "domain",
            sa.String(length=20),
            nullable=False,
            comment="Domain that was read (PeerShareDomain value).",
        ),
        sa.Column(
            "tool_name",
            sa.String(length=100),
            nullable=False,
            comment="Tool that performed the read (e.g. get_peer_availability).",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_peer_access_log_accessor_id", "peer_access_log", ["accessor_id"])
    op.create_index("ix_peer_access_log_created_at", "peer_access_log", ["created_at"])
    op.create_index("ix_peer_access_log_owner_created", "peer_access_log", ["owner_id", "created_at"])


def downgrade() -> None:
    """Drop the 5 peers tables (children first) + the users column."""
    op.drop_index("ix_peer_access_log_owner_created", table_name="peer_access_log")
    op.drop_index("ix_peer_access_log_created_at", table_name="peer_access_log")
    op.drop_index("ix_peer_access_log_accessor_id", table_name="peer_access_log")
    op.drop_table("peer_access_log")

    op.drop_index("ix_peer_messages_status_created", table_name="peer_messages")
    op.drop_index("ix_peer_messages_recipient_id", table_name="peer_messages")
    op.drop_index("ix_peer_messages_sender_id", table_name="peer_messages")
    op.drop_index("ix_peer_messages_connection_id", table_name="peer_messages")
    op.drop_table("peer_messages")

    op.drop_index("ix_peer_domain_shares_owner_user_id", table_name="peer_domain_shares")
    op.drop_index("ix_peer_domain_shares_connection_id", table_name="peer_domain_shares")
    op.drop_table("peer_domain_shares")

    op.drop_index("ix_peer_blocks_blocked_id", table_name="peer_blocks")
    op.drop_index("ix_peer_blocks_blocker_id", table_name="peer_blocks")
    op.drop_table("peer_blocks")

    op.drop_index("ix_peer_connections_status", table_name="peer_connections")
    op.drop_index("ix_peer_connections_user_b_id", table_name="peer_connections")
    op.drop_index("ix_peer_connections_user_a_id", table_name="peer_connections")
    op.drop_table("peer_connections")

    op.drop_column("users", "discovery_enabled")
