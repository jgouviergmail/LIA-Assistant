"""Create scheduled_actions table.

Revision ID: scheduled_actions_001
Revises: add_user_debug_panel_001
Create Date: 2026-02-27

Stores user-defined recurring actions with day-of-week + time scheduling.
The scheduler polls for due actions using next_trigger_at (UTC).
Includes a partial index for the scheduler hot path query.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "scheduled_actions_001"
down_revision: str | None = "add_user_debug_panel_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create scheduled_actions table with indexes."""
    op.create_table(
        "scheduled_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("action_prompt", sa.Text(), nullable=False),
        sa.Column(
            "days_of_week",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
            comment="ISO weekdays: 1=Monday..7=Sunday",
        ),
        sa.Column(
            "trigger_hour",
            sa.SmallInteger(),
            nullable=False,
            comment="Hour of execution (0-23) in user timezone",
        ),
        sa.Column(
            "trigger_minute",
            sa.SmallInteger(),
            nullable=False,
            comment="Minute of execution (0-59) in user timezone",
        ),
        sa.Column(
            "user_timezone",
            sa.String(50),
            nullable=False,
            server_default="Europe/Paris",
            comment="IANA timezone for schedule evaluation",
        ),
        sa.Column(
            "next_trigger_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Next execution time in UTC (computed from schedule + timezone)",
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="User toggle - False = paused",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="active -> executing -> active (recurring cycle)",
        ),
        sa.Column(
            "last_executed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful execution timestamp (UTC)",
        ),
        sa.Column(
            "execution_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Total successful executions",
        ),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Consecutive failure count (reset on success)",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="Last execution error message",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Standard indexes
    op.create_index("ix_scheduled_actions_user_id", "scheduled_actions", ["user_id"])
    op.create_index("ix_scheduled_actions_next_trigger_at", "scheduled_actions", ["next_trigger_at"])
    op.create_index("ix_scheduled_actions_status", "scheduled_actions", ["status"])

    # Partial index for scheduler hot path: only enabled + active actions
    op.create_index(
        "ix_scheduled_actions_due",
        "scheduled_actions",
        ["next_trigger_at"],
        postgresql_where=sa.text("is_enabled = true AND status = 'active'"),
    )


def downgrade() -> None:
    """Drop scheduled_actions table."""
    op.drop_index("ix_scheduled_actions_due", table_name="scheduled_actions")
    op.drop_index("ix_scheduled_actions_status", table_name="scheduled_actions")
    op.drop_index("ix_scheduled_actions_next_trigger_at", table_name="scheduled_actions")
    op.drop_index("ix_scheduled_actions_user_id", table_name="scheduled_actions")
    op.drop_table("scheduled_actions")
