"""Reserve visitor slots atomically instead of counting rows.

The demonstrator's daily signup ceiling counted ``users`` created since UTC
midnight and then let the caller insert. Measured 2026-08-07 against the
running instance: a ceiling of five, forty registrations released together by
a thread barrier, **37 accounts created**. Every request read the count before
any of them committed, so every request passed — the bound overshot 7,6x, and
what it bounds is the verification mail billed to the operator's smarthost.

A count followed by an insert is the shape CLAUDE.md forbids for concurrent
counters. This column carries the reservation instead, on the row that already
holds the instance's other per-UTC-day fact, and it moves only through a
conditional UPSERT (``ON CONFLICT DO UPDATE ... WHERE signup_count < :limit``)
whose row lock serialises the decision.

Revision ID: c7d1e93a4f10
Revises: 466cd37b0f44
Create Date: 2026-08-07 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d1e93a4f10"
down_revision: str | None = "466cd37b0f44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the reservation counter, defaulting to zero on existing rows."""
    op.add_column(
        "instance_daily_budget",
        sa.Column(
            "signup_count",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="Visitor slots reserved on that UTC day (demo mode).",
        ),
    )
    # Same shape as the money check constraint next to it: a negative
    # reservation count would mean the conditional UPSERT has been replaced by
    # arithmetic that can underflow.
    op.create_check_constraint(
        "ck_instance_daily_budget_signup_non_negative",
        "instance_daily_budget",
        "signup_count >= 0",
    )


def downgrade() -> None:
    """Drop it. The ceiling falls back to being unenforceable, not to counting."""
    op.drop_constraint(
        "ck_instance_daily_budget_signup_non_negative",
        "instance_daily_budget",
        type_="check",
    )
    op.drop_column("instance_daily_budget", "signup_count")
