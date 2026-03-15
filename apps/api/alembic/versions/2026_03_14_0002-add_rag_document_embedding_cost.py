"""Add embedding token/cost tracking columns to rag_documents.

Stores the token count and EUR cost of embedding each document,
so users can see indexation costs in the frontend.

Revision ID: rag_spaces_002
Revises: rag_spaces_001
Create Date: 2026-03-14 00:02:00.000000

Phase: evolution — RAG Spaces (User Knowledge Documents)
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "rag_spaces_002"
down_revision: str | None = "rag_spaces_001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "rag_documents",
        sa.Column(
            "embedding_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Total tokens consumed for embedding this document",
        ),
    )
    op.add_column(
        "rag_documents",
        sa.Column(
            "embedding_cost_eur",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Total embedding cost in EUR for this document",
        ),
    )


def downgrade() -> None:
    op.drop_column("rag_documents", "embedding_cost_eur")
    op.drop_column("rag_documents", "embedding_tokens")
