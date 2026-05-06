"""Stratified consciousness for personal journals.

Three-step migration that adds the foundations for the journal refactor
described in ADR-079:

* Step 1 — Observable foundation: epistemic status on entries
  (``confidence``, ``evidence_count``, ``contradiction_count``).
* Step 2 — Stratification: ``level`` column to classify entries on
  four abstraction levels (L0 observations, L1 directives, L2 patterns,
  L3 portrait facets).
* Step 3 — Portrait diffusion: three columns on ``users`` to persist
  the compiled user model portrait that LIA carries everywhere it
  speaks (full + brief formats + compilation timestamp).

All new columns are NULLABLE or carry a server default — code rollback
is possible without DB rollback. The downgrade reverses every step in
inverse order.

Revision ID: journals_stratified_001
Revises: llm_models_003
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "journals_stratified_001"
down_revision: str | None = "llm_models_003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the three-step upgrade in order."""
    # =========================================================================
    # Step 1 — Observable foundation (Commit 1)
    # =========================================================================
    op.add_column(
        "journal_entries",
        sa.Column(
            "confidence",
            sa.String(10),
            nullable=False,
            server_default="medium",
            comment="Epistemic status: low (hypothesis), medium (default), high (validated).",
        ),
    )
    op.add_column(
        "journal_entries",
        sa.Column(
            "evidence_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of times this entry was confirmed by deferred self-evaluation.",
        ),
    )
    op.add_column(
        "journal_entries",
        sa.Column(
            "contradiction_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of times this entry was contradicted by deferred self-evaluation.",
        ),
    )

    # =========================================================================
    # Step 2 — Stratification (Commit 2)
    # =========================================================================
    op.add_column(
        "journal_entries",
        sa.Column(
            "level",
            sa.String(2),
            nullable=False,
            server_default="L1",
            comment=(
                "Abstraction level: L0 raw observations, L1 operational directives, "
                "L2 transversal patterns, L3 portrait facets."
            ),
        ),
    )

    # =========================================================================
    # Step 3 — Portrait diffusion (Commit 3)
    # =========================================================================
    op.add_column(
        "users",
        sa.Column(
            "journal_portrait_full",
            sa.Text(),
            nullable=True,
            comment="Compiled user model portrait — full format (~200 tokens) for response/planner.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "journal_portrait_brief",
            sa.Text(),
            nullable=True,
            comment="Compiled user model portrait — brief format (~60 tokens) for secondary flows.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "journal_portrait_compiled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC timestamp of the last portrait compilation by the consolidation service.",
        ),
    )


def downgrade() -> None:
    """Reverse the three-step upgrade in inverse order."""
    # Step 3 reversed
    op.drop_column("users", "journal_portrait_compiled_at")
    op.drop_column("users", "journal_portrait_brief")
    op.drop_column("users", "journal_portrait_full")
    # Step 2 reversed
    op.drop_column("journal_entries", "level")
    # Step 1 reversed
    op.drop_column("journal_entries", "contradiction_count")
    op.drop_column("journal_entries", "evidence_count")
    op.drop_column("journal_entries", "confidence")
