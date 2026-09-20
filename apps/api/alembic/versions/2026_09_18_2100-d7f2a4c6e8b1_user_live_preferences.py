"""The person's live-conversation preferences (ADR-299).

One nullable JSONB column on ``users``: NULL means « every default », and the
tolerant reader never fails on what an older version wrote.

Revision ID: d7f2a4c6e8b1
Revises: c9e5a7b1d3f4
Create Date: 2026-09-18 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d7f2a4c6e8b1"
down_revision: str | None = "c9e5a7b1d3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = (
    "Live conversation preferences (interruptions, end of speech, result delivery, the "
    "provider the sessions open on)."
)


def upgrade() -> None:
    """Add the column, NULL for everyone."""
    op.add_column(
        "users",
        sa.Column(
            "live_preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=_COMMENT,
        ),
    )


def downgrade() -> None:
    """Drop the column."""
    op.drop_column("users", "live_preferences")
