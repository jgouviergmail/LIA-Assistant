"""Name an unserved routine's occupied account without claiming success.

Revision ID: e70f2a4b6c83
Revises: d69e1f3a5b72
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e70f2a4b6c83"
down_revision: str | Sequence[str] | None = "d69e1f3a5b72"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "scheduled_action_runs"
_CONSTRAINT = "scheduledrunoutcome"
_BEFORE = ("success", "failure", "skipped_condition", "proposed", "skipped_hitl")


def _outcomes(values: tuple[str, ...]) -> None:
    """Replace the finite CHECK and its documented vocabulary in the same transaction."""
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, sa.column("outcome").in_(values))
    op.alter_column(_TABLE, "outcome", comment=" | ".join(values))


def upgrade() -> None:
    """Allow explicit busy skips while preserving every old outcome."""
    _outcomes((*_BEFORE, "skipped_busy"))


def downgrade() -> None:
    """Refuse to erase or misclassify busy history that the old vocabulary cannot read."""
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM scheduled_action_runs WHERE outcome = 'skipped_busy')"
        )
    ):
        raise RuntimeError("Busy routine history requires the expanded outcome vocabulary")
    _outcomes(_BEFORE)
