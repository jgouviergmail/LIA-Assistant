"""Allow anonymous product events (ADR-178 Phase 4, arbitration a).

Pre-signup landing/demo funnel events carry no user: ``user_id`` becomes
nullable. Anonymous rows store counts only — no IP, no fingerprint, no
identifier of any kind — and follow the same retention purge.

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-07-29 06:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "c0d1e2f3a4b5"
down_revision: str | None = "b9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the NOT NULL on product_events.user_id."""
    op.alter_column(
        "product_events",
        "user_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    """Restore NOT NULL (anonymous rows are deleted first — they have no owner)."""
    op.execute(sa.text("DELETE FROM product_events WHERE user_id IS NULL"))
    op.alter_column(
        "product_events",
        "user_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
    )
