"""Gaps in the transparency record itself (ADR-263, lot 8).

The three registers say what LIA did, read and decided. This table says when
they could NOT: an effect performed with no ledger row, a turn whose
consultations nobody collected, a chain that stopped verifying, a sealing pass
rolled back.

Each of those already has a metric and an alert. A counter cannot say WHICH
accounts and WHICH turns are affected, and that is the question a user and a
regulator actually ask — hence a row rather than a fifth counter.

``user_id`` is nullable, and that is not laxity: one of the four detections
fires precisely when no run context named a user, and inventing one would erase
the interesting half of the finding. The FK still cascades, so a gap that DID
name an account leaves with it.

**This table must read as empty in production.** No index beyond its two reads:
it is not meant to grow.

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-09-05 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "b6c7d8e9f0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the integrity register."""
    op.create_table(
        "agent_integrity_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "kind",
            sa.String(length=40),
            nullable=False,
            comment="effect_unrecorded | treatments_uncollected | chain_broken | notary_failed",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
            comment="Whose account, when the detection knew. NULL = no run context named one.",
        ),
        sa.Column(
            "run_id",
            sa.String(length=100),
            nullable=True,
            comment="Which turn, when the detection knew.",
        ),
        sa.Column(
            "detail",
            sa.String(length=200),
            nullable=True,
            comment="SHORT bounded classification (a reason code, a position) — never content.",
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the gap was observed (UTC).",
        ),
        comment="Gaps in the transparency record itself (ADR-263, lot 8).",
    )
    op.create_index(
        "ix_agent_integrity_user_occurred", "agent_integrity_events", ["user_id", "occurred_at"]
    )
    op.create_index("ix_agent_integrity_occurred", "agent_integrity_events", ["occurred_at"])


def downgrade() -> None:
    """Drop it."""
    op.drop_index("ix_agent_integrity_occurred", table_name="agent_integrity_events")
    op.drop_index("ix_agent_integrity_user_occurred", table_name="agent_integrity_events")
    op.drop_table("agent_integrity_events")
