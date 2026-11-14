"""Count how often a person uses each skill.

Revision ID: c4d9e1f7a2b5
Revises: b6e2f48a1c93

A person could not see which of their skills LIA used, nor which ones sat
active and unused — each active skill still enters the analyzer's list on every
turn. ``user_skill_states`` gains the count of runs that used the skill, when
it was last used, the run last counted (one run counts once), when the counting
began, and when the person last chose to keep the skill after the proposal to
switch it off (the proposal then waits a whole period again). Zero and NULL for
every state that exists, and the counting begins NOW for them: nothing was
counted before this migration, so a skill used every day until today must not
read as « unused for months ». A stable default (``now()`` is the transaction's
time) keeps every addition a metadata-only change on PostgreSQL, no table
rewrite.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d9e1f7a2b5"
down_revision: str | Sequence[str] | None = "b6e2f48a1c93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "user_skill_states"


def upgrade() -> None:
    """Add the five columns: no state has been used yet, and counting begins now."""
    op.add_column(
        _TABLE,
        sa.Column(
            "use_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Runs in which this skill was used for this user, one per run.",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When a run last used this skill for this user; NULL = never.",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "last_used_run_id",
            sa.String(length=64),
            nullable=True,
            comment="The run last counted, so one run counts once.",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "usage_counted_since",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When counting began: this migration for an existing state, creation after.",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "dormancy_kept_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the person last kept this skill after the unused-skill proposal.",
        ),
    )


def downgrade() -> None:
    """Drop the counts: what was used is forgotten."""
    op.drop_column(_TABLE, "dormancy_kept_at")
    op.drop_column(_TABLE, "usage_counted_since")
    op.drop_column(_TABLE, "last_used_run_id")
    op.drop_column(_TABLE, "last_used_at")
    op.drop_column(_TABLE, "use_count")
