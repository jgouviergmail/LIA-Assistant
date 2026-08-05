"""habits: learned rhythm profile + discrete habits (ADR-214)

Two tables and one user preference:

- user_habit_profiles: one row per user, the nightly-recomputed rhythm
  profile. DERIVED data — always recomputable from conversation history, so
  a deleted conversation naturally leaves the profile at the next recompute.
- user_habits: discrete promoted habits (active windows, locked recurring
  requests) with feedback signals and a user-controlled status; BLOCKED rows
  are tombstones that prevent relearning.
- users.habits_enabled: user master toggle (server_default true — the global
  HABITS_ENABLED flag defaults OFF, so nothing changes until the operator
  opts in; the user toggle then governs learning AND consumption).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-05 12:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_habit_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Versioned rhythm profile (histograms, windows, verdicts).",
        ),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source_max_created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Delta-skip marker: newest source message the profile saw.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "user_habits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Kind-specific versioned payload (windows / schedule shape).",
        ),
        sa.Column("positive_signals", sa.Integer(), nullable=False),
        sa.Column("negative_signals", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "muted_until_reproof",
            sa.Boolean(),
            nullable=False,
            comment="Deviation stop-rule: type-1 offers muted until re-occurrence.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "key", name="uq_user_habits_user_kind_key"),
    )
    op.create_index("ix_user_habits_user_kind", "user_habits", ["user_id", "kind"])
    op.create_index("ix_user_habits_user_status", "user_habits", ["user_id", "status"])

    op.create_table(
        "user_activity_days",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column(
            "hour_counts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Per-hour human-message counts for the day (no content).",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "local_date", name="uq_user_activity_days_user_date"),
    )
    op.create_index(
        "ix_user_activity_days_user_date", "user_activity_days", ["user_id", "local_date"]
    )

    op.add_column(
        "users",
        sa.Column(
            "habits_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Enable learned-habits profile and consumption.",
        ),
    )

    # Feedback loop: a 👍/👎 on a heartbeat notification that carried a
    # missed-routine offer bumps the habit's signals. SET NULL keeps the
    # audit row when the habit is deleted.
    op.add_column(
        "heartbeat_notifications",
        sa.Column(
            "habit_offer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_habits.id", ondelete="SET NULL"),
            nullable=True,
            comment="Habit surfaced as a missed-routine offer, if any.",
        ),
    )


def downgrade() -> None:
    op.drop_column("heartbeat_notifications", "habit_offer_id")
    op.drop_index("ix_user_activity_days_user_date", table_name="user_activity_days")
    op.drop_table("user_activity_days")
    op.drop_column("users", "habits_enabled")
    op.drop_index("ix_user_habits_user_status", table_name="user_habits")
    op.drop_index("ix_user_habits_user_kind", table_name="user_habits")
    op.drop_table("user_habits")
    op.drop_table("user_habit_profiles")
