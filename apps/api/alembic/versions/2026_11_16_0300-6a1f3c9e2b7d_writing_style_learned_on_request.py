"""A writing style is learned when the person asks: ``built_at`` says so (ADR-383).

Revision ID: 6a1f3c9e2b7d
Revises: 4cbcd1e424fd
Create Date: 2026-11-16 03:00:00.000000

Since the amendment of 2026-11-16 a profile is learned at the person's request — their
click in the settings or their word to the assistant — and never expires on its own:
nothing learns it again « once too old ». The model's column comment says so; column
comments are part of the structural schema check (``schema_drift.py``), so the database
is told the same in a revision of its own. Comment only: no data moves.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6a1f3c9e2b7d"
down_revision: str | None = "4cbcd1e424fd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FORMER_COMMENT = "When the profile was learned (UTC); it is learned again once too old."
_ON_REQUEST_COMMENT = "When the profile was learned (UTC), at the person's request."


def _comment(new: str, former: str) -> None:
    op.alter_column(
        "writing_styles",
        "built_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        comment=new,
        existing_comment=former,
    )


def upgrade() -> None:
    """Say the profile is learned at the person's request."""
    _comment(_ON_REQUEST_COMMENT, _FORMER_COMMENT)


def downgrade() -> None:
    """Restore the former comment."""
    _comment(_FORMER_COMMENT, _ON_REQUEST_COMMENT)
