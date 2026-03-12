"""Add interests learning system

Revision ID: add_interests_system_001
Revises: add_user_font_family_001
Create Date: 2026-01-26 00:00:00.000000

This migration creates the interests learning system:

1. User preferences columns:
   - interests_enabled: Feature toggle (opt-in, default False)
   - interests_notify_start_hour: Notification window start (default 9)
   - interests_notify_end_hour: Notification window end (default 22)
   - interests_notify_min_per_day: Min notifications per day (default 1)
   - interests_notify_max_per_day: Max notifications per day (default 3)

2. user_interests table:
   - Stores user interests extracted from conversations
   - Bayesian weight system (positive/negative signals)
   - pgvector embedding for deduplication
   - Status tracking (active/blocked/dormant)

3. interest_notifications table:
   - Audit trail for sent notifications
   - Deduplication via content_hash and content_embedding
   - User feedback tracking (thumbs_up/thumbs_down/block)
   - run_id for token tracking linkage
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_interests_system_001"
down_revision: str | None = "add_user_font_family_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add interests system: user preferences, interests table, notifications table.
    """
    # =========================================================================
    # 1. Add user preference columns for interests
    # =========================================================================

    # Feature toggle (opt-in, disabled by default)
    op.add_column(
        "users",
        sa.Column(
            "interests_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Enable proactive interest notifications (opt-in feature).",
        ),
    )

    # Notification time window
    op.add_column(
        "users",
        sa.Column(
            "interests_notify_start_hour",
            sa.Integer(),
            nullable=False,
            server_default="9",
            comment="Start hour for interest notifications (0-23, user timezone).",
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "interests_notify_end_hour",
            sa.Integer(),
            nullable=False,
            server_default="22",
            comment="End hour for interest notifications (0-23, user timezone).",
        ),
    )

    # Notification frequency
    op.add_column(
        "users",
        sa.Column(
            "interests_notify_min_per_day",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Minimum interest notifications per day (1-5).",
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "interests_notify_max_per_day",
            sa.Integer(),
            nullable=False,
            server_default="3",
            comment="Maximum interest notifications per day (1-5).",
        ),
    )

    # =========================================================================
    # 2. Create user_interests table
    # =========================================================================
    op.create_table(
        "user_interests",
        # Primary key
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Foreign key to users
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Interest content
        sa.Column(
            "topic",
            sa.String(200),
            nullable=False,
            comment="Interest topic (e.g., 'iOS, Apple smartphones', 'machine learning')",
        ),
        sa.Column(
            "category",
            sa.String(50),
            nullable=False,
            comment="Category: technology/science/culture/sports/finance/travel/nature/health/entertainment/other",
        ),
        # Bayesian weight signals
        sa.Column(
            "positive_signals",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Count of positive signals (mentions, thumbs up).",
        ),
        sa.Column(
            "negative_signals",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of negative signals (thumbs down, decay).",
        ),
        # Status
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="Status: active/blocked/dormant",
        ),
        # Activity timestamps
        sa.Column(
            "last_mentioned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Last time user mentioned this interest in conversation.",
        ),
        sa.Column(
            "last_notified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last time a notification was sent for this interest.",
        ),
        sa.Column(
            "dormant_since",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When interest became dormant (for auto-deletion).",
        ),
        # Embedding for deduplication (pgvector, 384 dims for E5-small)
        sa.Column(
            "embedding",
            postgresql.ARRAY(sa.Float()),
            nullable=True,
            comment="E5-small embedding (384 dims) for semantic deduplication.",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Unique constraint on (user_id, topic)
    op.create_unique_constraint(
        "uq_user_interests_user_topic",
        "user_interests",
        ["user_id", "topic"],
    )

    # Index for user queries
    op.create_index(
        "ix_user_interests_user_id",
        "user_interests",
        ["user_id"],
    )

    # Index for status queries (active interests)
    op.create_index(
        "ix_user_interests_user_status",
        "user_interests",
        ["user_id", "status"],
    )

    # Partial index for scheduler: only active interests
    op.create_index(
        "ix_user_interests_active",
        "user_interests",
        ["user_id", "last_notified_at"],
        postgresql_where=sa.text("status = 'active'"),
    )

    # =========================================================================
    # 3. Create interest_notifications table
    # =========================================================================
    op.create_table(
        "interest_notifications",
        # Primary key
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Foreign keys
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "interest_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_interests.id", ondelete="SET NULL"),
            nullable=True,
            comment="Interest that was notified (NULL if interest deleted).",
        ),
        # Token tracking linkage
        sa.Column(
            "run_id",
            sa.String(100),
            nullable=False,
            unique=True,
            comment="Unique run_id linking to token_usage_logs and message_token_summary.",
        ),
        # Deduplication
        sa.Column(
            "content_hash",
            sa.String(64),
            nullable=False,
            comment="SHA256 hash of content for exact deduplication.",
        ),
        sa.Column(
            "content_embedding",
            postgresql.ARRAY(sa.Float()),
            nullable=True,
            comment="E5-small embedding (384 dims) for semantic deduplication.",
        ),
        # Content source
        sa.Column(
            "source",
            sa.String(50),
            nullable=False,
            comment="Content source: wikipedia/perplexity/llm_reflection",
        ),
        # User feedback
        sa.Column(
            "user_feedback",
            sa.String(20),
            nullable=True,
            comment="User feedback: thumbs_up/thumbs_down/null",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Index for user queries (daily quota check)
    op.create_index(
        "ix_interest_notifications_user_created",
        "interest_notifications",
        ["user_id", "created_at"],
    )

    # Index for interest cooldown queries
    op.create_index(
        "ix_interest_notifications_interest_created",
        "interest_notifications",
        ["interest_id", "created_at"],
    )

    # Index for content hash lookups (deduplication)
    op.create_index(
        "ix_interest_notifications_content_hash",
        "interest_notifications",
        ["user_id", "content_hash"],
    )


def downgrade() -> None:
    """
    Drop interests system tables and columns.
    """
    # Drop interest_notifications indexes and table
    op.drop_index("ix_interest_notifications_content_hash", table_name="interest_notifications")
    op.drop_index("ix_interest_notifications_interest_created", table_name="interest_notifications")
    op.drop_index("ix_interest_notifications_user_created", table_name="interest_notifications")
    op.drop_table("interest_notifications")

    # Drop user_interests indexes and table
    op.drop_index("ix_user_interests_active", table_name="user_interests")
    op.drop_index("ix_user_interests_user_status", table_name="user_interests")
    op.drop_index("ix_user_interests_user_id", table_name="user_interests")
    op.drop_constraint("uq_user_interests_user_topic", "user_interests", type_="unique")
    op.drop_table("user_interests")

    # Drop user columns
    op.drop_column("users", "interests_notify_max_per_day")
    op.drop_column("users", "interests_notify_min_per_day")
    op.drop_column("users", "interests_notify_end_hour")
    op.drop_column("users", "interests_notify_start_hour")
    op.drop_column("users", "interests_enabled")
