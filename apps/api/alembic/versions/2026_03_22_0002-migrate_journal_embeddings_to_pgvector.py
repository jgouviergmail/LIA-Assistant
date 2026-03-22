"""Migrate journal embeddings from E5-small ARRAY to OpenAI pgvector.

Replaces the E5-small (384d) ARRAY(Float()) column with OpenAI
text-embedding-3-small (1536d) pgvector Vector column.

DESTRUCTIVE: Purges all existing journal entries because embeddings
are incompatible between the two models (384d vs 1536d).

Adds HNSW index for efficient cosine distance search.

Revision ID: journal_pgvector_001
Revises: journal_search_hints_001
Create Date: 2026-03-22
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision = "journal_pgvector_001"
down_revision = "journal_search_hints_001"
branch_labels = None
depends_on = None

# pgvector extension is already enabled (from RAG spaces migration)
EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    # 1. Purge all entries (embeddings are incompatible between E5-small and OpenAI)
    op.execute(sa.text("DELETE FROM journal_entries"))

    # 2. Drop old ARRAY(Float()) embedding column
    op.drop_column("journal_entries", "embedding")

    # 3. Add new pgvector Vector column
    op.add_column(
        "journal_entries",
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
    )

    # 4. Add HNSW index for cosine distance search
    op.create_index(
        "ix_journal_entries_embedding_cosine",
        "journal_entries",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    # Drop HNSW index
    op.drop_index("ix_journal_entries_embedding_cosine", table_name="journal_entries")

    # Drop pgvector column
    op.drop_column("journal_entries", "embedding")

    # Restore ARRAY(Float()) column
    op.add_column(
        "journal_entries",
        sa.Column(
            "embedding",
            sa.ARRAY(sa.Float()),
            nullable=True,
        ),
    )
