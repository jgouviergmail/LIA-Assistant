"""proactive discussion policies claims and publication

Revision ID: 7a1c9e042f60
Revises: 9e6bc702d1f4
Create Date: 2026-10-20 09:51:54.973366

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7a1c9e042f60"
down_revision: str | None = "9e6bc702d1f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discussion_preferences",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("start_hour", sa.Integer(), server_default=sa.text("9"), nullable=False),
        sa.Column("end_hour", sa.Integer(), server_default=sa.text("20"), nullable=False),
        sa.Column("daily_max", sa.Integer(), server_default=sa.text("2"), nullable=True),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "sensitive_topics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("context_epoch", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("run_fence", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("active_run_id", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(active_run_id IS NULL) = (lease_until IS NULL)", name="ck_discussion_lease_pair"
        ),
        sa.CheckConstraint("daily_max IS NULL OR daily_max > 0", name="ck_discussion_max"),
        sa.CheckConstraint(
            "revision >= 0 AND run_fence >= 0 AND context_epoch >= 0",
            name="ck_discussion_revisions",
        ),
        sa.CheckConstraint(
            "start_hour BETWEEN 0 AND 23 AND end_hour BETWEEN 0 AND 23 AND start_hour <> end_hour",
            name="ck_discussion_hours",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_discussion_preferences_owner"),
    )
    op.create_index(
        "ix_discussion_candidates",
        "discussion_preferences",
        ["enabled", "paused_until", "user_id"],
        unique=False,
    )
    op.create_table(
        "discussion_runs",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("fence", sa.BigInteger(), nullable=False),
        sa.Column("policy_revision", sa.BigInteger(), nullable=False),
        sa.Column("context_epoch", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('claimed', 'completed', 'skipped', 'failed', 'abandoned')",
            name="ck_discussion_run_state",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "fence", name="uq_discussion_run_fence"),
        sa.UniqueConstraint("user_id", "id", name="uq_discussion_run_owner_id"),
    )
    op.create_index(
        "ix_discussion_runs_owner_date", "discussion_runs", ["user_id", "claimed_at"], unique=False
    )
    op.create_table(
        "discussion_openings",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("topic", sa.String(length=256), nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("references", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("policy_revision", sa.BigInteger(), nullable=False),
        sa.Column("context_epoch", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sensitive_context", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('pending', 'engaged', 'dismissed', 'expired')",
            name="ck_discussion_opening_state",
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["conversation_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["user_id", "run_id"],
            ["discussion_runs.user_id", "discussion_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
        sa.UniqueConstraint("run_id"),
        sa.UniqueConstraint("user_id", "fingerprint", name="uq_discussion_opening_fingerprint"),
        sa.UniqueConstraint("user_id", "id", name="uq_discussion_opening_owner_id"),
    )
    op.create_index(
        "ix_discussion_openings_owner_date",
        "discussion_openings",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_discussion_pending_owner",
        "discussion_openings",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("state = 'pending'"),
    )
    op.create_table(
        "discussion_outbox",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("opening_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("attempt_token", sa.Uuid(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('pending', 'dispatching', 'delivered', 'failed', 'uncertain', 'cancelled')",
            name="ck_discussion_outbox_state",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "opening_id"],
            ["discussion_openings.user_id", "discussion_openings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("opening_id"),
    )
    op.create_index(
        "ix_discussion_outbox_pending", "discussion_outbox", ["state", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_discussion_outbox_pending", table_name="discussion_outbox")
    op.drop_table("discussion_outbox")
    op.drop_index(
        "uq_discussion_pending_owner",
        table_name="discussion_openings",
        postgresql_where=sa.text("state = 'pending'"),
    )
    op.drop_index("ix_discussion_openings_owner_date", table_name="discussion_openings")
    op.drop_table("discussion_openings")
    op.drop_index("ix_discussion_runs_owner_date", table_name="discussion_runs")
    op.drop_table("discussion_runs")
    op.drop_index("ix_discussion_candidates", table_name="discussion_preferences")
    op.drop_table("discussion_preferences")
