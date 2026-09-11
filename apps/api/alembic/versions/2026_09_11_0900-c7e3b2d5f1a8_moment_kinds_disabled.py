"""Let a person refuse a kind of anticipated moment (ADR-281, lot 2).

The control before the exploitation: lot 1 ships one kind and one switch — the
operator's. Without this column an account whose deployment has the capability
on can refuse nothing, and the next lot adds three kinds more.

Stored as the REFUSAL set (ADR-197's doctrine, second vocabulary): NULL means
« never expressed », so every existing account behaves exactly as before, and a
kind shipped later is on until somebody turns it off rather than invisible until
everybody opts back in.

Revision ID: c7e3b2d5f1a8
Revises: b4f2a1c9d3e7
Create Date: 2026-09-11 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c7e3b2d5f1a8"
down_revision: str | None = "b4f2a1c9d3e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = "Anticipated-moment kinds the user refused; NULL = all enabled."


def upgrade() -> None:
    """Add the nullable refusal column."""
    op.add_column(
        "users",
        sa.Column(
            "moment_kinds_disabled",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=_COMMENT,
        ),
    )


def downgrade() -> None:
    """Drop it. A refusal lost on downgrade re-enables the kind, which is the
    safe direction: the person can refuse it again, and nothing was silenced."""
    op.drop_column("users", "moment_kinds_disabled")
