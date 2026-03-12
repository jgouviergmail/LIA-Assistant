"""Add heartbeat autonome (proactive notifications).

Revision ID: heartbeat_001
Revises: channel_bindings_001
Create Date: 2026-03-03

Add 3 user columns for heartbeat settings and create heartbeat_notifications
audit table for proactive notification tracking.

Phase: evolution F5 — Heartbeat Autonome LLM
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "heartbeat_001"
down_revision: str | None = "channel_bindings_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add heartbeat user columns and create heartbeat_notifications table."""
    # --- User columns (non-blocking: all have server_default) ---
    op.add_column(
        "users",
        sa.Column(
            "heartbeat_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="Enable proactive heartbeat notifications (opt-in).",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "heartbeat_max_per_day",
            sa.Integer,
            nullable=False,
            server_default=sa.text("3"),
            comment="Maximum heartbeat notifications per day (1-8).",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "heartbeat_push_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
            comment=(
                "Enable push (FCM/Telegram) for heartbeats. "
                "If false, only SSE + archive."
            ),
        ),
    )

    # --- Heartbeat notifications audit table ---
    op.create_table(
        "heartbeat_notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.String(100),
            nullable=False,
            unique=True,
            comment="Unique ID linking to token tracking.",
        ),
        sa.Column(
            "content",
            sa.Text,
            nullable=False,
            comment="The notification message sent to the user.",
        ),
        sa.Column(
            "content_hash",
            sa.String(64),
            nullable=False,
            comment="SHA256 hash for exact deduplication.",
        ),
        sa.Column(
            "sources_used",
            sa.Text,
            nullable=False,
            comment="JSON list of source types used (e.g. calendar, weather).",
        ),
        sa.Column(
            "decision_reason",
            sa.Text,
            nullable=True,
            comment="LLM's reason for deciding to notify.",
        ),
        sa.Column(
            "priority",
            sa.String(10),
            nullable=False,
            server_default=sa.text("'low'"),
            comment="Notification priority: low, medium, high.",
        ),
        sa.Column(
            "user_feedback",
            sa.String(20),
            nullable=True,
            comment="User feedback: thumbs_up or thumbs_down.",
        ),
        sa.Column(
            "tokens_in",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "tokens_out",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "model_name",
            sa.String(100),
            nullable=True,
        ),
    )

    # Composite index for user history queries
    op.create_index(
        "ix_heartbeat_notifications_user_created",
        "heartbeat_notifications",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    """Remove heartbeat notifications table and user columns."""
    op.drop_index(
        "ix_heartbeat_notifications_user_created",
        table_name="heartbeat_notifications",
    )
    op.drop_table("heartbeat_notifications")

    op.drop_column("users", "heartbeat_push_enabled")
    op.drop_column("users", "heartbeat_max_per_day")
    op.drop_column("users", "heartbeat_enabled")
