"""One row per tick of a routine (ADR-265).

The weekly timeline colours each cell of the current week — executed, failed,
not run — and a colour is a claim: it needs a record of WHAT happened at WHICH
slot. Nothing held that record: ``scheduled_actions`` keeps one
``last_executed_at`` and one ``last_error`` without a timestamp, and the turn
register files a scheduled turn under its CONVERSATION id, not its routine.

Written by the executor at the RESULT, in the same transaction as the
success/failure marking, never before it. A crash mid-run leaves no row, which
is the truth. Five outcomes, one per executor exit, so the two skips and the
proposal are recorded rather than read as silence.

Bounded: ``SCHEDULED_ACTIONS_RUNS_RETENTION_DAYS``, purged inside the
executor's own tick.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-09-05 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the run history."""
    op.create_table(
        "scheduled_action_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scheduled_action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scheduled_actions.id", ondelete="CASCADE"),
            nullable=False,
            comment="The routine. Dies with it.",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="Whose routine — denormalised for the week read and the export.",
        ),
        sa.Column(
            "slot_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="The scheduled instant this run served (UTC); NULL = a rehearsal.",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the tick started (UTC).",
        ),
        sa.Column(
            "ended_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the outcome was known (UTC).",
        ),
        sa.Column(
            "outcome",
            sa.Enum(
                "success",
                "failure",
                "skipped_condition",
                "proposed",
                "skipped_hitl",
                name="scheduledrunoutcome",
                native_enum=False,
                length=20,
                create_constraint=True,
            ),
            nullable=False,
            comment="success | failure | skipped_condition | proposed | skipped_hitl",
        ),
        sa.Column(
            "attempts",
            sa.SmallInteger(),
            nullable=False,
            comment="Pipeline attempts made (retries included); 0 when it never ran.",
        ),
        sa.Column(
            "manual",
            sa.Boolean(),
            nullable=False,
            comment="True = started by the user (Test now), not by a due slot.",
        ),
        sa.Column(
            "error",
            sa.Text(),
            nullable=True,
            comment="Last error message of a FAILURE, truncated.",
        ),
    )
    op.create_index(
        "ix_scheduled_action_runs_action_slot",
        "scheduled_action_runs",
        ["scheduled_action_id", "slot_at"],
    )
    op.create_index(
        "ix_scheduled_action_runs_user_started",
        "scheduled_action_runs",
        ["user_id", "started_at"],
    )
    op.create_index("ix_scheduled_action_runs_started", "scheduled_action_runs", ["started_at"])


def downgrade() -> None:
    """Drop it."""
    op.drop_index("ix_scheduled_action_runs_started", table_name="scheduled_action_runs")
    op.drop_index("ix_scheduled_action_runs_user_started", table_name="scheduled_action_runs")
    op.drop_index("ix_scheduled_action_runs_action_slot", table_name="scheduled_action_runs")
    op.drop_table("scheduled_action_runs")
