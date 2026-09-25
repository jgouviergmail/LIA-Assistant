"""A generated image can be shared with a connection (ADR-316).

Revision ID: fe0475369c8e
Revises: 79db1056a28e
Create Date: 2026-09-24 21:00:00.000000

Two changes, one feature:

- ``peer_image_shares`` — the ledger of one share: who shared with whom, on
  which connection, and which copy it produced in the recipient's gallery. The
  sender's daily quotas count these rows (the copy itself expires with the
  attachment TTL). No comment is stored: it reaches the recipient's chat and
  nowhere else.
- ``attachments.shared_by_name`` — on the recipient's copy, the display name of
  the connection who shared it, so the gallery can say where an image it did
  not generate came from. NULL on every existing row.

Downgrade drops both: the previous code reads neither.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "fe0475369c8e"
down_revision: str | None = "79db1056a28e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the share ledger and the provenance column."""
    op.create_table(
        "peer_image_shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Connection the image travelled on.",
        ),
        sa.Column(
            "sender_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="User who shared the image.",
        ),
        sa.Column(
            "recipient_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="User who received a copy in their gallery.",
        ),
        sa.Column(
            "attachment_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="The recipient's copy; NULL once it expired or was deleted.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["peer_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attachment_id"], ["attachments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_peer_image_shares_connection_id", "peer_image_shares", ["connection_id"])
    op.create_index("ix_peer_image_shares_recipient_id", "peer_image_shares", ["recipient_id"])
    op.create_index("ix_peer_image_shares_attachment_id", "peer_image_shares", ["attachment_id"])
    op.create_index(
        "ix_peer_image_shares_sender_created",
        "peer_image_shares",
        ["sender_id", "created_at"],
    )
    op.add_column(
        "attachments",
        sa.Column(
            "shared_by_name",
            # As wide as users.full_name, the value it snapshots.
            sa.String(length=255),
            nullable=True,
            comment="Display name of the connection who shared this image (ADR-316); NULL otherwise.",
        ),
    )


def downgrade() -> None:
    """Drop the provenance column and the share ledger."""
    op.drop_column("attachments", "shared_by_name")
    op.drop_index("ix_peer_image_shares_sender_created", table_name="peer_image_shares")
    op.drop_index("ix_peer_image_shares_attachment_id", table_name="peer_image_shares")
    op.drop_index("ix_peer_image_shares_recipient_id", table_name="peer_image_shares")
    op.drop_index("ix_peer_image_shares_connection_id", table_name="peer_image_shares")
    op.drop_table("peer_image_shares")
