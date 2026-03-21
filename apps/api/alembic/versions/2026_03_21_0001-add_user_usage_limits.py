"""Add user_usage_limits table.

Per-user usage limits for tokens, messages, and cost enforcement.
One record per user (1:1 relationship). Null limits mean unlimited.

Revision ID: usage_limits_001
Revises: hue_global_config_001
Create Date: 2026-03-21
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "usage_limits_001"
down_revision = "hue_global_config_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create user_usage_limits table."""
    op.create_table(
        "user_usage_limits",
        # Primary key (UUIDMixin)
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        # User reference (1:1)
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Per-cycle limits (None = unlimited)
        sa.Column("token_limit_per_cycle", sa.BigInteger, nullable=True),
        sa.Column("message_limit_per_cycle", sa.BigInteger, nullable=True),
        sa.Column("cost_limit_per_cycle", sa.Numeric(12, 6), nullable=True),
        # Absolute/lifetime limits (None = unlimited)
        sa.Column("token_limit_absolute", sa.BigInteger, nullable=True),
        sa.Column("message_limit_absolute", sa.BigInteger, nullable=True),
        sa.Column("cost_limit_absolute", sa.Numeric(12, 6), nullable=True),
        # Manual block
        sa.Column(
            "is_usage_blocked",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
        sa.Column("blocked_reason", sa.String(500), nullable=True),
        sa.Column(
            "blocked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "blocked_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        # Timestamps (TimestampMixin)
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
    )

    # Unique index on user_id (1:1 relationship)
    op.create_index(
        "ix_user_usage_limits_user_id",
        "user_usage_limits",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    """Drop user_usage_limits table."""
    op.drop_index("ix_user_usage_limits_user_id", table_name="user_usage_limits")
    op.drop_table("user_usage_limits")
