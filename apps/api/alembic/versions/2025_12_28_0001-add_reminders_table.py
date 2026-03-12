"""Add reminders table for user reminders

Revision ID: add_memos_table_001
Revises: add_user_last_login_001
Create Date: 2025-12-28 00:00:00.000000

This migration creates the reminders table for storing user reminders.

Features:
- User reminders with trigger time (stored in UTC)
- Status tracking (pending → processing → cancelled, deleted after notification)
- Retry mechanism for failed notifications
- Partial indexes for scheduler performance
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_memos_table_001"
down_revision: str | None = "add_user_last_login_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Create reminders table with indexes.
    """
    op.create_table(
        "reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        # Content
        sa.Column("content", sa.Text(), nullable=False, comment="What the user wants to be reminded of"),
        sa.Column("original_message", sa.Text(), nullable=False, comment="Original user message for LLM context"),
        # Scheduling (UTC)
        sa.Column("trigger_at", sa.DateTime(timezone=True), nullable=False, comment="When to send the reminder (UTC)"),
        sa.Column("user_timezone", sa.String(50), nullable=False, server_default="Europe/Paris", comment="User timezone at creation time"),
        # Status
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", comment="pending/processing/cancelled (deleted after notification)"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0", comment="Number of notification attempts"),
        # Audit
        sa.Column("notification_error", sa.Text(), nullable=True, comment="Error message if failed"),
        # Timestamps (from BaseModel)
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    # Index for user queries
    op.create_index(
        "ix_reminders_user_id",
        "reminders",
        ["user_id"],
    )

    # Index for trigger time queries
    op.create_index(
        "ix_reminders_trigger_at",
        "reminders",
        ["trigger_at"],
    )

    # Partial index for scheduler: only pending reminders
    op.create_index(
        "ix_reminders_pending_trigger",
        "reminders",
        ["trigger_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # Partial index for processing reminders (for cleanup)
    op.create_index(
        "ix_reminders_processing",
        "reminders",
        ["status"],
        postgresql_where=sa.text("status = 'processing'"),
    )


def downgrade() -> None:
    """
    Drop reminders table.
    """
    op.drop_index("ix_reminders_processing", table_name="reminders")
    op.drop_index("ix_reminders_pending_trigger", table_name="reminders")
    op.drop_index("ix_reminders_trigger_at", table_name="reminders")
    op.drop_index("ix_reminders_user_id", table_name="reminders")
    op.drop_table("reminders")
