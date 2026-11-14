"""Three override rows whose slot no code declares leave the table.

Revision ID: 27fc835b8d44
Revises: 45cf916cc02f
Create Date: 2026-11-11 22:00:00.000000

ADR-244 took three rows out of the reference seed -- ``router`` and
``context_resolver``, slots no ``get_llm()`` caller asked for, and
``mcp_excalidraw``, a row for a slot the registry never held -- and no migration
followed: an instance seeded before it kept them (read on production and on the
development instance on 2026-11-11). Nothing reads these rows and no screen
shows them, so only an extraction finds them again: regenerating the seed from
production had to leave the three out by hand.

The names are one bound list, matched exactly. ``RETIRED`` is held against the
registry, the code defaults and the factory's vocabulary by
``test_orphan_slot_rows_migration_guard.py``: a name any of them declared would
be a row an administrator configured.

The downgrade writes nothing back: the code falls back on a slot's default when
it has no row, and no code reads these three.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "27fc835b8d44"
down_revision: str | None = "45cf916cc02f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: The rows ADR-244 removed from the seed and left on the instances.
RETIRED: tuple[str, ...] = ("context_resolver", "mcp_excalidraw", "router")

RETIRE_THE_ROWS = sa.text("DELETE FROM llm_config_overrides WHERE llm_type IN :slots").bindparams(
    sa.bindparam("slots", expanding=True)
)


def upgrade() -> None:
    """Remove the three rows where an instance still holds them."""
    removed = op.get_bind().execute(RETIRE_THE_ROWS, {"slots": list(RETIRED)}).rowcount
    logger.info("orphan slot rows: %d removed", removed)


def downgrade() -> None:
    """Write nothing back: no code reads these rows."""
