"""The decision register says its ``execution_mode`` is the ENGINE that ran (ADR-390).

Revision ID: d7f104891aef
Revises: aec0910ecebe
Create Date: 2026-11-15 15:00:00.000000

Since the automatic mode, ``agent_decisions.execution_mode`` holds the engine the
router settled (``pipeline`` or ``react``) — what was asked, « auto » included, moved
to ``requested_mode`` — and, outside the graph, how the run ran. The model's column
comment says so; column comments are part of the structural schema check
(``schema_drift.py``), so the database is told the same in a revision of its own,
which an instance already at ``aec0910ecebe`` applies too. Comment only: no data moves.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7f104891aef"
down_revision: str | None = "aec0910ecebe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FORMER_COMMENT = "pipeline | react | subagent"
_ENGINE_COMMENT = (
    "The engine the router settled (pipeline | react); until it did, what was "
    "asked (auto included); outside the graph, how the run ran (subagent | direct)."
)


def _comment(new: str, former: str) -> None:
    op.alter_column(
        "agent_decisions",
        "execution_mode",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        comment=new,
        existing_comment=former,
    )


def upgrade() -> None:
    """Say the column holds the engine."""
    _comment(_ENGINE_COMMENT, _FORMER_COMMENT)


def downgrade() -> None:
    """Restore the former comment."""
    _comment(_FORMER_COMMENT, _ENGINE_COMMENT)
