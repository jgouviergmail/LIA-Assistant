"""Widen product_events.event_type to 64 chars.

Per-mission showroom vocabulary reaches 39 chars
(``demo_mission_started_overloaded_morning``) while the column was
``String(32)``: every such INSERT failed with
StringDataRightTruncationError and the guided-showroom funnel silently
lost its per-mission rows. The enum/column fit is now guarded (derived
from the model) by
``tests/unit/domains/product/test_product_constants.py``.

Revision ID: 8a9b0c1d2e3f
Revises: 7f8a9b0c1d2e
Create Date: 2026-08-20 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8a9b0c1d2e3f"
down_revision: str | None = "7f8a9b0c1d2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Widen event_type to the guarded capacity (pure metadata change)."""
    op.alter_column(
        "product_events",
        "event_type",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Shrink back to 32 — rows that would not fit are deleted first.

    Those rows can only be the per-mission showroom events this migration
    exists to admit; keeping them would make the ALTER fail outright.
    """
    op.execute(sa.text("DELETE FROM product_events WHERE char_length(event_type) > 32"))
    op.alter_column(
        "product_events",
        "event_type",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
