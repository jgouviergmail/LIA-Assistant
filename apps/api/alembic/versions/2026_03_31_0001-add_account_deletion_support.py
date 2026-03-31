"""Add account deletion support (soft-delete with billing preservation).

Adds deleted_at and deleted_reason columns to users table for the
account lifecycle: Active → Deactivated → Deleted → Erased (GDPR).

Also fixes FK constraints that would block GDPR hard-delete:
- google_api_usage_logs.user_id: CASCADE → SET NULL (preserve billing data)
- admin_broadcasts.sent_by: add ondelete SET NULL (prevent FK violation)

Revision ID: account_deletion_001
Revises: create_memories_001
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "account_deletion_001"
down_revision: str | None = "create_memories_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add account deletion columns and fix FK constraints."""
    # 1. Add deleted_at and deleted_reason to users
    op.add_column(
        "users",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of account deletion. NULL = active/inactive. "
            "Non-NULL = deleted (data purged, row kept for billing).",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "deleted_reason",
            sa.String(500),
            nullable=True,
            comment="Admin-provided reason for account deletion.",
        ),
    )
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])

    # 2. Fix google_api_usage_logs.user_id: CASCADE → SET NULL + nullable
    # Preserve billing history when user row is hard-deleted (GDPR)
    op.drop_constraint(
        "google_api_usage_logs_user_id_fkey",
        "google_api_usage_logs",
        type_="foreignkey",
    )
    op.alter_column(
        "google_api_usage_logs",
        "user_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_foreign_key(
        "google_api_usage_logs_user_id_fkey",
        "google_api_usage_logs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. Fix admin_broadcasts.sent_by: add ondelete SET NULL + nullable
    # Prevent FK violation when admin user is hard-deleted
    op.drop_constraint(
        "fk_admin_broadcasts_sent_by",
        "admin_broadcasts",
        type_="foreignkey",
    )
    op.alter_column(
        "admin_broadcasts",
        "sent_by",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_foreign_key(
        "fk_admin_broadcasts_sent_by",
        "admin_broadcasts",
        "users",
        ["sent_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove account deletion columns and restore FK constraints."""
    # 3. Restore admin_broadcasts.sent_by FK (no ondelete)
    op.drop_constraint(
        "fk_admin_broadcasts_sent_by",
        "admin_broadcasts",
        type_="foreignkey",
    )
    op.alter_column(
        "admin_broadcasts",
        "sent_by",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_admin_broadcasts_sent_by",
        "admin_broadcasts",
        "users",
        ["sent_by"],
        ["id"],
    )

    # 2. Restore google_api_usage_logs.user_id FK (CASCADE + non-nullable)
    op.drop_constraint(
        "google_api_usage_logs_user_id_fkey",
        "google_api_usage_logs",
        type_="foreignkey",
    )
    op.alter_column(
        "google_api_usage_logs",
        "user_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "google_api_usage_logs_user_id_fkey",
        "google_api_usage_logs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 1. Remove deleted_at and deleted_reason from users
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_column("users", "deleted_reason")
    op.drop_column("users", "deleted_at")
