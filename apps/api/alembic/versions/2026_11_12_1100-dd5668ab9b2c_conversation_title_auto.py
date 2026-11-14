"""Let an annex wait for its first message to give it its title.

Revision ID: dd5668ab9b2c
Revises: 1e2baddce0fe

A discussion could only be created with a typed title. ``title_auto`` marks an
annex created without one: it holds a placeholder until its owner's first
message names it, once (ADR-378 amendment 2026-11-12). Every existing row was
titled by its owner or is Main, so the column starts false everywhere — a
metadata-only change on PostgreSQL, no table rewrite.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "dd5668ab9b2c"
down_revision: str | Sequence[str] | None = "1e2baddce0fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "conversations"
_COLUMN = "title_auto"


def upgrade() -> None:
    """Add the flag, false for every discussion that exists."""
    op.add_column(
        _TABLE,
        sa.Column(
            _COLUMN,
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="True while an annex waits for its first message to give it its title.",
        ),
    )


def downgrade() -> None:
    """Drop the flag: a waiting annex keeps its placeholder as an ordinary title."""
    op.drop_column(_TABLE, _COLUMN)
