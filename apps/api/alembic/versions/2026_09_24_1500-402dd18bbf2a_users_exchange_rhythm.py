"""The account's exchange rhythm: what the ReAct loop shapes its prompt for (ADR-311).

Revision ID: 402dd18bbf2a
Revises: b2e6d0f4a8c1
Create Date: 2026-09-24 15:00:00.000000

``users.exchange_rhythm`` holds the person's choice — ``frequent`` (every tool
bound, the prompt shaped for the next turn's cache) or ``occasional`` (the
relevance selection). The column is NULLABLE and filled by nobody here: NULL
means « never chosen », and such an account follows
``REACT_CROSS_TURN_CACHE_ENABLED``, the operator's default — so no deployment
changes behaviour when the column appears. The downgrade drops the column; the
previous code reads the setting alone.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "402dd18bbf2a"
down_revision: str | None = "b2e6d0f4a8c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable preference column."""
    op.add_column(
        "users",
        sa.Column(
            "exchange_rhythm",
            sa.String(length=20),
            nullable=True,
            comment=(
                "Exchange rhythm preference: 'frequent' (every tool bound, prompt shaped for "
                "the next turn's cache) or 'occasional' (relevance selection); NULL = instance "
                "default."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the column: the previous code reads the instance setting alone."""
    op.drop_column("users", "exchange_rhythm")
