"""Why a turn stopped short (ADR-263, lot 8).

A column, deliberately, and not a table. ``agent_decisions`` already says a
turn ended ``interrupted``; what was missing is WHY — a budget, an iteration
ceiling, a compute timeout. Two columns, two facts: the outcome stays what it
is and this says what stopped it.

The value comes from ``react_exit_reason``, the ONE predicate that decides the
stop (ADR-248 invariant 2). Recording a reason computed anywhere else would be
a third opinion on the same question, and the loop has already paid for that
mistake once.

Nullable: a turn that ran to its natural end has no reason to give, and NULL
says exactly that.

Revision ID: b6c7d8e9f0a1
Revises: f3c4d5e6a7b8
Create Date: 2026-09-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6c7d8e9f0a1"
down_revision: str | None = "f3c4d5e6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the stop reason."""
    op.add_column(
        "agent_decisions",
        sa.Column(
            "stop_reason",
            sa.String(length=40),
            nullable=True,
            comment="Why the turn stopped short (max_iterations | compute_budget | ...); "
            "NULL when it ran to its natural end. ADR-263 lot 8.",
        ),
    )


def downgrade() -> None:
    """Drop it."""
    op.drop_column("agent_decisions", "stop_reason")
