"""A kept answer is projected into the « Kept answers » knowledge space (2026-09-16 design, part A).

Three columns on ``message_bookmarks``: the RAG document the answer is
projected into (``SET NULL`` — losing the projection never loses the
bookmark), why there is no projection yet, and when it last reached READY.
Every existing row starts at ``NULL``: the reconciliation sweep projects the
backlog.

Revision ID: d5e0a2b4f6c8
Revises: c4d9f1a3e5b7
Create Date: 2026-09-16 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d5e0a2b4f6c8"
down_revision: str | None = "c4d9f1a3e5b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RAG_DOCUMENT_ID_COMMENT = (
    "The RAG document this answer is projected into, while it exists (2026-09-16 design)."
)
_INDEX_STATE_COMMENT = (
    "Why there is no projection yet (pending | indexed | error | deferred | disabled); "
    "NULL = never attempted. The document row is the authority while it exists."
)
_INDEXED_AT_COMMENT = "When the projection last reached READY."


def upgrade() -> None:
    """Add the projection columns, NULL for every existing bookmark."""
    op.add_column(
        "message_bookmarks",
        sa.Column(
            "rag_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rag_documents.id", ondelete="SET NULL"),
            nullable=True,
            comment=_RAG_DOCUMENT_ID_COMMENT,
        ),
    )
    op.add_column(
        "message_bookmarks",
        sa.Column("index_state", sa.String(length=20), nullable=True, comment=_INDEX_STATE_COMMENT),
    )
    op.add_column(
        "message_bookmarks",
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=_INDEXED_AT_COMMENT,
        ),
    )
    # The reconciliation sweep reads « bookmarks with no projection », least
    # recently attempted first (every state write stamps updated_at); the sweep
    # is bounded, so the scan must be too.
    op.create_index(
        "ix_message_bookmarks_unprojected",
        "message_bookmarks",
        ["updated_at"],
        postgresql_where=sa.text("rag_document_id IS NULL"),
    )


def downgrade() -> None:
    """Drop the projection columns; the documents themselves stay in the space."""
    op.drop_index("ix_message_bookmarks_unprojected", table_name="message_bookmarks")
    op.drop_column("message_bookmarks", "indexed_at")
    op.drop_column("message_bookmarks", "index_state")
    op.drop_column("message_bookmarks", "rag_document_id")
