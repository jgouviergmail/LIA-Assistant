"""Name a routine its account's usage ceiling stood aside, without calling it a failure.

Revision ID: 1e2baddce0fe
Revises: f302f3667c58

A routine of an account past its usage ceiling used to leave no run row at all
(the tick returned before any settle and the routine stayed ``executing`` until
the stale recovery), and a ceiling met inside the turn was filed as a
``failure`` — five of them paused the routine. ``skipped_quota`` is the reason
the week now shows for such a slot (ADR-265 amendment 2026-11-12, ADR-272).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1e2baddce0fe"
down_revision: str | Sequence[str] | None = "f302f3667c58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "scheduled_action_runs"
_CONSTRAINT = "scheduledrunoutcome"
_BEFORE = ("success", "failure", "skipped_condition", "proposed", "skipped_hitl", "skipped_busy")


def _outcomes(values: tuple[str, ...]) -> None:
    """Replace the finite CHECK and its documented vocabulary in the same transaction."""
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, sa.column("outcome").in_(values))
    op.alter_column(_TABLE, "outcome", comment=" | ".join(values))


def upgrade() -> None:
    """Allow explicit usage-ceiling skips while preserving every old outcome."""
    _outcomes((*_BEFORE, "skipped_quota"))


def downgrade() -> None:
    """Refuse to erase or misclassify quota history that the old vocabulary cannot read."""
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM scheduled_action_runs WHERE outcome = 'skipped_quota')"
        )
    ):
        raise RuntimeError("Quota routine history requires the expanded outcome vocabulary")
    _outcomes(_BEFORE)
