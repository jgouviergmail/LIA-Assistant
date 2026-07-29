"""Add condition triggers + approval to scheduled_actions (N-07 phase 1).

UX Actions program, lot F: routines evolve from time-only to "time OR
condition-gated" (evaluated at the cron tick, deduped by fingerprint) with an
optional propose-first mode. Existing rows keep their exact behavior:
trigger_kind backfills to 'time' and requires_approval to false. See ADR-175.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-29 03:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the four N-07 columns; server defaults keep existing rows 'time'."""
    op.add_column(
        "scheduled_actions",
        sa.Column(
            "trigger_kind",
            sa.String(length=20),
            nullable=False,
            server_default="time",
            comment="time = fire at every tick; condition = fire only when met (N-07)",
        ),
    )
    op.add_column(
        "scheduled_actions",
        sa.Column(
            "condition_config",
            JSONB,
            nullable=True,
            comment="CONDITION kind only: {type, params} — schema-validated.",
        ),
    )
    op.add_column(
        "scheduled_actions",
        sa.Column(
            "condition_state",
            JSONB,
            nullable=True,
            comment="Dedup ledger: {last_fingerprint, last_fired_at}.",
        ),
    )
    op.add_column(
        "scheduled_actions",
        sa.Column(
            "requires_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True = propose via notification (?intent= link) instead of executing.",
        ),
    )


def downgrade() -> None:
    """Drop the N-07 columns — time routines are untouched either way."""
    op.drop_column("scheduled_actions", "requires_approval")
    op.drop_column("scheduled_actions", "condition_state")
    op.drop_column("scheduled_actions", "condition_config")
    op.drop_column("scheduled_actions", "trigger_kind")
