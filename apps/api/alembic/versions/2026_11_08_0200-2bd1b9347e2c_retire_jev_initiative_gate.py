"""The JEV initiative utility gate leaves with its switch and slot (ADR-374).

Revision ID: 2bd1b9347e2c
Revises: 9f4f6c3bb223
Create Date: 2026-11-08 02:00:00.000000

The gate told no state apart (0.67 to 0.77 where the evaluator acts, 0.41 to 0.81 elsewhere)
and production never saw it answer « nothing useful »: the evaluator it guarded runs on every
eligible tool turn. The code no longer declares ``JEV_INITIATIVE_UTILITY_ENABLED``,
so its row would make every unfiltered read of ``system_settings`` raise ``LookupError``; this
migration runs before that code boots. The downgrade writes nothing: the former code reads a
missing switch as off, and a missing slot row as that slot's default.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2bd1b9347e2c"
down_revision: str | None = "9f4f6c3bb223"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RETIRE_THE_SWITCH = sa.text(
    "DELETE FROM system_settings WHERE key = 'JEV_INITIATIVE_UTILITY_ENABLED'"
)
_RETIRE_THE_SLOT = sa.text(
    "DELETE FROM llm_config_overrides WHERE llm_type = 'jev_initiative_utility'"
)


def upgrade() -> None:
    """Remove the rows of the retired switch and slot."""
    op.execute(_RETIRE_THE_SWITCH)
    op.execute(_RETIRE_THE_SLOT)


def downgrade() -> None:
    """Write nothing back: a missing switch reads as off, a missing slot as its default."""
