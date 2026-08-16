"""Backfill product_outcomes.result_type for actionable chat runs.

``derive_result_type`` compared the router intention against ``"actionable"``,
a value no router has ever emitted — the router node persists ``"action"``
(``INTENTION_ACTION``). Every actionable chat run was therefore recorded as
``answer``, which E2 behavioral validation never promotes: the dashboard's
"successful actions" tile stayed at zero and "confirmed useful results"
degenerated to successful routine runs alone.

The code fix aligns the comparison with the router vocabulary for FUTURE runs.
This migration repairs the HISTORY: the correct classification is mechanically
derivable (no invented intent) because the assistant message archived for each
run carries the router intention verbatim in its metadata. Rows reclassified to
``action`` that are still ``produced``, uncorrected and unreverted are promoted
to E2 by the next ``product_rollup`` pass — the dashboard then reflects the
true history of the billing cycle, not just runs after the deploy.

Scheduler runs are untouched: their rows are ``automation_run`` (channel takes
precedence over intention), which the ``result_type = 'answer'`` filter
excludes by construction.

Revision ID: 1f2a3b4c5d6e
Revises: 0d1e2f3a4b5c
Create Date: 2026-08-16 14:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1f2a3b4c5d6e"
down_revision: str | None = "0d1e2f3a4b5c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Reclassify chat outcomes whose archived intention was ``action``."""
    op.execute(
        """
        UPDATE product_outcomes po
        SET result_type = 'action'
        WHERE po.result_type = 'answer'
          AND EXISTS (
            SELECT 1
            FROM conversation_messages m
            WHERE m.role = 'assistant'
              AND m.message_metadata->>'run_id' = po.run_id
              AND m.message_metadata->>'intention' = 'action'
          )
        """
    )


def downgrade() -> None:
    """Restore the pre-fix classification (every chat run an ``answer``).

    Faithful reverse: before the vocabulary fix, no code path could produce an
    ``action`` row (proven on production data — zero rows), so mapping every
    ``action`` back to ``answer`` reproduces the exact pre-migration state.
    """
    op.execute("UPDATE product_outcomes SET result_type = 'answer' WHERE result_type = 'action'")
