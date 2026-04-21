"""Rename steps_cumulative → steps and purge incompatible demo rows.

The Health Metrics ingestion contract was clarified after the initial design:
the iPhone Shortcut sends the steps count for the current period (since the
last sample), NOT the daily cumulative counter. The column name is updated
accordingly, and any pre-existing rows that were ingested under the previous
"cumulative" semantics are removed (they would otherwise display as
nonsensical increments under the new aggregation logic).

Revision ID: health_metrics_002
Revises: health_metrics_001
Create Date: 2026-04-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "health_metrics_002"
down_revision: str | None = "health_metrics_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_COMMENT = "Steps recorded during the inter-sample period " "(NOT a daily cumulative counter)."
_OLD_COMMENT = "Cumulative daily step count. NULL if not provided or out of range."


def upgrade() -> None:
    """Drop pre-existing rows then rename the column to its corrected name."""
    # Pre-rename data is semantically incompatible (cumulative vs increment).
    op.execute("DELETE FROM health_metrics")
    op.alter_column(
        "health_metrics",
        "steps_cumulative",
        new_column_name="steps",
        existing_type=sa.Integer(),
        existing_nullable=True,
        existing_comment=_OLD_COMMENT,
        comment=_NEW_COMMENT,
    )


def downgrade() -> None:
    """Revert the column name (data is not restored)."""
    op.alter_column(
        "health_metrics",
        "steps",
        new_column_name="steps_cumulative",
        existing_type=sa.Integer(),
        existing_nullable=True,
        existing_comment=_NEW_COMMENT,
        comment=_OLD_COMMENT,
    )
