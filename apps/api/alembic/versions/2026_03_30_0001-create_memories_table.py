"""Create memories table for PostgreSQL-based memory storage.

Migrates memory persistence from LangGraph AsyncPostgresStore to a dedicated
SQLAlchemy table with pgvector HNSW index for semantic search.

The LangGraph store is preserved for tool context, heartbeat context,
and future documents. Only the memories namespace is migrated.

Data migration is handled by a separate script (scripts/migrate_memories_to_postgresql.py).

Revision ID: create_memories_001
Revises: embeddings_e5_to_openai_001
Create Date: 2026-03-30
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "create_memories_001"
down_revision = "embeddings_e5_to_openai_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create memories table with pgvector HNSW index."""
    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Content
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        # Qualification
        sa.Column("emotional_weight", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trigger_topic", sa.String(100), nullable=False, server_default=""),
        sa.Column("usage_nuance", sa.String(300), nullable=False, server_default=""),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.7"),
        # Phase 6 lifecycle tracking
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default="false"),
        # Semantic embedding (OpenAI text-embedding-3-small: 1536 dims)
        sa.Column("embedding", Vector(1536), nullable=True),
        # Size tracking
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        # Timestamps (BaseModel pattern)
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Composite indexes for common query patterns
    op.create_index("ix_memories_user_created", "memories", ["user_id", "created_at"])
    op.create_index("ix_memories_user_category", "memories", ["user_id", "category"])

    # pgvector HNSW index for efficient cosine distance search
    # Same parameters as journal_entries embedding index
    op.execute(
        """
        CREATE INDEX ix_memories_embedding_cosine
        ON memories USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    """Drop memories table.

    Data in the LangGraph store (if preserved) serves as fallback.
    """
    op.drop_index("ix_memories_embedding_cosine", table_name="memories")
    op.drop_index("ix_memories_user_category", table_name="memories")
    op.drop_index("ix_memories_user_created", table_name="memories")
    op.drop_table("memories")
