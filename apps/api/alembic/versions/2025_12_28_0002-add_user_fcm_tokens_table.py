"""Add user_fcm_tokens table.

Revision ID: 2025_12_28_0002
Revises: 2025_12_28_0001
Create Date: 2025-12-28

FCM tokens for Firebase Cloud Messaging push notifications.
Each user can have multiple tokens (one per device).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "add_fcm_tokens_001"
down_revision = "add_memos_table_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create user_fcm_tokens table."""
    op.create_table(
        "user_fcm_tokens",
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
            comment="Owner of the FCM token",
        ),
        sa.Column(
            "token",
            sa.Text(),
            nullable=False,
            comment="Firebase Cloud Messaging token",
        ),
        sa.Column(
            "device_type",
            sa.String(20),
            nullable=False,
            comment="Device type: 'android', 'ios', 'web'",
        ),
        sa.Column(
            "device_name",
            sa.String(100),
            nullable=True,
            comment="Human-readable device name",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether the token is active",
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last time a notification was sent to this token",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="Last FCM error for this token",
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
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token", name="uq_user_fcm_tokens_token"),
    )

    # Indexes
    op.create_index(
        "ix_user_fcm_tokens_user_id",
        "user_fcm_tokens",
        ["user_id"],
    )

    # Partial index for active tokens (most common query)
    op.create_index(
        "ix_user_fcm_tokens_user_active",
        "user_fcm_tokens",
        ["user_id"],
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    """Drop user_fcm_tokens table."""
    op.drop_index("ix_user_fcm_tokens_user_active", table_name="user_fcm_tokens")
    op.drop_index("ix_user_fcm_tokens_user_id", table_name="user_fcm_tokens")
    op.drop_table("user_fcm_tokens")
