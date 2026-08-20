"""Memory supersession trail (Lot 2-B1, ADR-235).

An automated correction (extraction update/delete, consolidation merge)
never destroys history anymore: the old fact leaves the active set
(``invalidated_at``) and, when replaced, points at its successor
(``superseded_by_id``). Every retrieval path filters the active set, so
these columns are invisible to search; the cleanup job purges the trail
past ``MEMORY_INVALIDATED_RETENTION_DAYS``.

Both columns are nullable with no backfill: every existing row is active
by definition. The partial index serves the ubiquitous
``invalidated_at IS NULL`` predicate. The index is ALSO declared in
``Memory.__table_args__`` — an index living only in a migration makes
autogenerate propose its DROP (ADR-228 trap).

Revision ID: 7f8a9b0c1d2e
Revises: 6e7f8a9b0c1d
Create Date: 2026-08-19 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "7f8a9b0c1d2e"
down_revision: str | None = "6e7f8a9b0c1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the supersession trail columns and their active-set index."""
    op.add_column(
        "memories",
        sa.Column(
            "invalidated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the fact left the active set; NULL = active.",
        ),
    )
    op.add_column(
        "memories",
        sa.Column(
            "superseded_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="SET NULL"),
            nullable=True,
            comment="Successor row when the fact was replaced (NULL on plain invalidation).",
        ),
    )
    op.create_index(
        "ix_memories_user_invalidated",
        "memories",
        ["user_id", "invalidated_at"],
    )


def downgrade() -> None:
    """Drop the trail columns and index (rows created invalidated are lost)."""
    op.drop_index("ix_memories_user_invalidated", table_name="memories")
    op.drop_column("memories", "superseded_by_id")
    op.drop_column("memories", "invalidated_at")
