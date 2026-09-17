"""A document's failure is named by a code, translated at display (ADR-184).

One nullable column on ``rag_documents``: the closed vocabulary of why the
indexing failed (``RAGDocumentErrorCode``), written beside ``error_message``
on the same update. NULL for every existing row and for every document that
succeeds; the technical message keeps carrying the detail.

Revision ID: a7c3e5b9d1f2
Revises: e6f1b3c5a7d9
Create Date: 2026-09-17 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e5b9d1f2"
down_revision: str | None = "e6f1b3c5a7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = (
    "Why the indexing failed, as a closed vocabulary (RAGDocumentErrorCode) the "
    "frontend translates; NULL when the document is not in error or the failure predates it."
)


def upgrade() -> None:
    """Add the code column, NULL for every existing row."""
    op.add_column(
        "rag_documents",
        sa.Column("error_code", sa.String(length=64), nullable=True, comment=_COMMENT),
    )


def downgrade() -> None:
    """Drop the column; the technical message stays."""
    op.drop_column("rag_documents", "error_code")
