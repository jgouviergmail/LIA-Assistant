"""Persist each knowledge space's owner favorite preference.

Revision ID: ea21f834b670
Revises: d94b62a10e73
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ea21f834b670"
down_revision: str | Sequence[str] | None = "d94b62a10e73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Keep existing spaces unfavorited without changing their activation."""
    op.add_column(
        "rag_spaces",
        sa.Column(
            "is_favorite",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="Owner's display preference, independent of retrieval activation",
        ),
    )


def downgrade() -> None:
    """Remove only the display preference."""
    op.drop_column("rag_spaces", "is_favorite")
