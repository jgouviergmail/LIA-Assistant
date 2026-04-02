"""Add keyword_embedding columns to memories and journal_entries.

Restores multi-vector search strategy that was lost during the
LangGraph store → PostgreSQL migration (v1.13.6). The old store
indexed content and trigger_topic as SEPARATE vectors; the new
custom tables concatenated them into a single embedding, causing
search quality degradation (signal dilution).

New strategy:
- embedding: content only (memories) / title+content (journals)
- keyword_embedding: trigger_topic (memories) / search_hints (journals)
- Search uses LEAST(dist_content, dist_keyword) for best match

Requires reindex after deployment (scripts/reindex_embeddings.py).

Revision ID: keyword_embedding_001
Revises: psyche_defaults_001
Create Date: 2026-04-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "keyword_embedding_001"
down_revision: str | None = "psyche_defaults_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add keyword_embedding columns and HNSW indexes."""
    # 1. memories.keyword_embedding
    op.add_column(
        "memories",
        sa.Column("keyword_embedding", Vector(1536), nullable=True),
    )
    op.execute(
        """
        CREATE INDEX ix_memories_keyword_embedding_cosine
        ON memories USING hnsw (keyword_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # 2. journal_entries.keyword_embedding
    op.add_column(
        "journal_entries",
        sa.Column("keyword_embedding", Vector(1536), nullable=True),
    )
    op.execute(
        """
        CREATE INDEX ix_journal_entries_keyword_embedding_cosine
        ON journal_entries USING hnsw (keyword_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    """Remove keyword_embedding columns and indexes."""
    op.drop_index(
        "ix_journal_entries_keyword_embedding_cosine",
        table_name="journal_entries",
    )
    op.drop_column("journal_entries", "keyword_embedding")

    op.drop_index(
        "ix_memories_keyword_embedding_cosine",
        table_name="memories",
    )
    op.drop_column("memories", "keyword_embedding")
