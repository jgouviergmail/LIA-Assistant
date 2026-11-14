"""Name an occurrence the scheduler reached past its catch-up window.

Revision ID: 7a3c9e51d4b8
Revises: dd5668ab9b2c

A due occurrence used to run however late the scheduler reached it — a morning
routine answered in the afternoon after an outage. It is now run late only
inside a catch-up window; past it the occurrence is not run, and
``skipped_late`` is the reason the week shows for its slot (ADR-265 amendment
2026-11-12 b).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a3c9e51d4b8"
down_revision: str | Sequence[str] | None = "dd5668ab9b2c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "scheduled_action_runs"
_CONSTRAINT = "scheduledrunoutcome"
_BEFORE = (
    "success",
    "failure",
    "skipped_condition",
    "proposed",
    "skipped_hitl",
    "skipped_busy",
    "skipped_quota",
)


def _outcomes(values: tuple[str, ...]) -> None:
    """Replace the finite CHECK and its documented vocabulary in the same transaction."""
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, sa.column("outcome").in_(values))
    op.alter_column(_TABLE, "outcome", comment=" | ".join(values))


def upgrade() -> None:
    """Allow explicit lateness skips while preserving every old outcome."""
    _outcomes((*_BEFORE, "skipped_late"))


def downgrade() -> None:
    """Refuse to erase or misclassify missed occurrences the old vocabulary cannot read."""
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM scheduled_action_runs WHERE outcome = 'skipped_late')"
        )
    ):
        raise RuntimeError("Missed routine history requires the expanded outcome vocabulary")
    _outcomes(_BEFORE)
