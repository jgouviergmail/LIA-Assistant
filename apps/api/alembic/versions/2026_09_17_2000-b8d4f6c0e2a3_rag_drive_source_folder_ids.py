"""A linked Drive folder is a tree: the walked folder ids travel with the source.

One JSONB column on ``rag_drive_sources``: the ids of the root and of every
sub-folder the last full synchronisation walked. A Drive push names a file's
PARENT, and since the synchronisation indexes sub-folders, a parent that is a
sub-folder must route to its source — matching the root alone left every
nested change invisible to the push path. Empty for every existing row (the
root alone routes until the next synchronisation walks the tree).

Revision ID: b8d4f6c0e2a3
Revises: a7c3e5b9d1f2
Create Date: 2026-09-17 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b8d4f6c0e2a3"
down_revision: str | None = "a7c3e5b9d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = (
    "Drive folder ids of the linked tree (root first) as of the last walk; "
    "the set a push change is routed on. Empty before the first walk."
)


def upgrade() -> None:
    """Add the folder-ids column, empty for every existing source."""
    op.add_column(
        "rag_drive_sources",
        sa.Column(
            "folder_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment=_COMMENT,
        ),
    )


def downgrade() -> None:
    """Drop the column; the root folder id stays on the row."""
    op.drop_column("rag_drive_sources", "folder_ids")
