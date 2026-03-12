"""Add admin_broadcasts and user_broadcast_reads tables.

Revision ID: add_admin_broadcast_001
Revises: change_interest_uniqueness_001
Create Date: 2026-01-30 00:00:00.000000

Admin broadcast messaging system for sending important messages to all users.
- admin_broadcasts: Stores broadcast messages sent by admins
- user_broadcast_reads: Tracks which users have read which broadcasts
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "add_admin_broadcast_001"
down_revision: str | None = "change_interest_uniqueness_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create admin_broadcasts and user_broadcast_reads tables."""
    # Admin Broadcasts table
    op.create_table(
        "admin_broadcasts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "message",
            sa.Text(),
            nullable=False,
            comment="The broadcast message content",
        ),
        sa.Column(
            "sent_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Admin user who sent the broadcast",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the broadcast expires (null = never)",
        ),
        sa.Column(
            "total_recipients",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Total number of active users at send time",
        ),
        sa.Column(
            "fcm_sent",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Number of FCM notifications successfully sent",
        ),
        sa.Column(
            "fcm_failed",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Number of FCM notifications that failed",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["sent_by"],
            ["users.id"],
            name="fk_admin_broadcasts_sent_by",
        ),
    )

    # Index on created_at for ordering
    op.create_index(
        "ix_admin_broadcasts_created_at",
        "admin_broadcasts",
        ["created_at"],
    )

    # User Broadcast Reads table
    op.create_table(
        "user_broadcast_reads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="User who read the broadcast",
        ),
        sa.Column(
            "broadcast_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Broadcast that was read",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_broadcast_reads_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["broadcast_id"],
            ["admin_broadcasts.id"],
            name="fk_user_broadcast_reads_broadcast_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "user_id",
            "broadcast_id",
            name="uq_user_broadcast_read",
        ),
    )

    # Index on user_id for efficient unread query
    op.create_index(
        "ix_user_broadcast_reads_user_id",
        "user_broadcast_reads",
        ["user_id"],
    )


def downgrade() -> None:
    """Drop admin_broadcasts and user_broadcast_reads tables."""
    op.drop_index("ix_user_broadcast_reads_user_id", table_name="user_broadcast_reads")
    op.drop_table("user_broadcast_reads")
    op.drop_index("ix_admin_broadcasts_created_at", table_name="admin_broadcasts")
    op.drop_table("admin_broadcasts")
