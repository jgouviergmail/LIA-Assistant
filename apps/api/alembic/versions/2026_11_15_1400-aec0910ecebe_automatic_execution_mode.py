"""The automatic execution mode files how each turn was resolved (ADR-390).

Revision ID: aec0910ecebe
Revises: 5ad5dfadfe7a
Create Date: 2026-11-15 14:00:00.000000

``agent_decisions`` gains what the turn was asked to run in (``requested_mode``) and
why the router chose its engine (``resolution_reason``), both nullable: a turn filed
before this revision, or a run outside the graph, has neither. The new decision usage
(``JEV_EXECUTION_MODE_*``) needs no row: a missing switch reads as off, missing
thresholds as their declared margins, a missing slot as its default.

The downgrade removes what the former code cannot read: the usage's rows
(``Enum(native_enum=False)`` raises ``LookupError`` on an undeclared member on every
unfiltered read of ``system_settings``) and its slot's configuration. « auto » is not a
choice the former code accepts — its schemas validate ``pipeline | react`` — so a
person who chose it reads ``pipeline`` again, and a ticket or a routine ``react``, the
default each row was born with.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aec0910ecebe"
down_revision: str | None = "5ad5dfadfe7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FORGET_THE_USAGE = sa.text(
    "DELETE FROM system_settings "
    "WHERE key IN ('JEV_EXECUTION_MODE_ENABLED', 'JEV_EXECUTION_MODE_THRESHOLDS')"
)
_FORGET_THE_SLOT = sa.text("DELETE FROM llm_config_overrides WHERE llm_type = 'jev_execution_mode'")
_CHOICES_THE_FORMER_CODE_READS = (
    ("users", "pipeline"),
    ("workboard_tickets", "react"),
    ("scheduled_actions", "react"),
)


def upgrade() -> None:
    """Add the two columns that say how a turn's engine was chosen."""
    op.add_column(
        "agent_decisions",
        sa.Column(
            "requested_mode",
            sa.String(length=20),
            nullable=True,
            comment="What the turn was asked to run in (pipeline | react | auto); NULL "
            "outside the graph and for turns filed before ADR-390.",
        ),
    )
    op.add_column(
        "agent_decisions",
        sa.Column(
            "resolution_reason",
            sa.String(length=32),
            nullable=True,
            comment="Why the router chose the engine (EngineReason, ADR-390); NULL for a "
            "turn no engine planned.",
        ),
    )


def downgrade() -> None:
    """Remove what the former code cannot read, and the two columns."""
    for table, fallback in _CHOICES_THE_FORMER_CODE_READS:
        op.execute(
            sa.text(
                f"UPDATE {table} SET execution_mode = :fallback WHERE execution_mode = 'auto'"
            ).bindparams(fallback=fallback)
        )
    op.execute(_FORGET_THE_USAGE)
    op.execute(_FORGET_THE_SLOT)
    op.drop_column("agent_decisions", "resolution_reason")
    op.drop_column("agent_decisions", "requested_mode")
