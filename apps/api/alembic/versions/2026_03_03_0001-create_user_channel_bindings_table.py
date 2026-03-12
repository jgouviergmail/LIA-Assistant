"""Create user_channel_bindings table.

Revision ID: channel_bindings_001
Revises: user_mcp_servers_002
Create Date: 2026-03-03

Generic table for linking LIA users to external messaging channels.
Telegram is the first channel type; the schema supports future additions.

Phase: evolution F3 — Multi-Channel Telegram Integration
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "channel_bindings_001"
down_revision: str | None = "user_mcp_servers_002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create user_channel_bindings table with constraints and indexes."""
    op.create_table(
        "user_channel_bindings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "channel_type",
            sa.String(20),
            nullable=False,
            comment="Channel type discriminant (e.g., 'telegram')",
        ),
        sa.Column(
            "channel_user_id",
            sa.String(100),
            nullable=False,
            comment="Provider-specific user identifier (e.g., Telegram chat_id)",
        ),
        sa.Column(
            "channel_username",
            sa.String(255),
            nullable=True,
            comment="Provider-specific display name (e.g., Telegram @username)",
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether this binding is active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Unique constraints
        sa.UniqueConstraint(
            "user_id", "channel_type", name="uq_user_channel_binding_type"
        ),
        sa.UniqueConstraint(
            "channel_type", "channel_user_id", name="uq_channel_type_user_id"
        ),
    )

    # Partial index for fast webhook lookup (hot path)
    op.create_index(
        "ix_channel_bindings_active_lookup",
        "user_channel_bindings",
        ["channel_type", "channel_user_id"],
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    """Drop user_channel_bindings table."""
    op.drop_index(
        "ix_channel_bindings_active_lookup",
        table_name="user_channel_bindings",
    )
    op.drop_table("user_channel_bindings")
