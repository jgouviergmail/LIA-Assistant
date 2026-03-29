"""Migrate embeddings from E5-small (384 dims) to OpenAI text-embedding-3-small (1536 dims).

Drops LangGraph-managed store_vectors table (auto-recreated with new dimensions on startup).
Nulls out interest embeddings (incompatible dimensions, re-embedded on next use).

Revision ID: embeddings_e5_to_openai_001
Revises: image_generation_001
Create Date: 2026-03-29
"""

from alembic import op

revision = "embeddings_e5_to_openai_001"
down_revision = "image_generation_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop store_vectors (384-dim) and null out interest embeddings.

    LangGraph AsyncPostgresStore.setup() will auto-recreate store_vectors
    with vector(1536) on next application startup.

    Interest embeddings will be re-generated on next use via OpenAI API.
    """
    # 1. Drop LangGraph-managed store_vectors table
    # CASCADE drops the HNSW index and FK constraints
    op.execute("DROP TABLE IF EXISTS store_vectors CASCADE")

    # 2. Reset LangGraph vector migration tracker so setup() recreates store_vectors
    # with new dimensions on next startup.
    # LangGraph tracks vector migrations separately in vector_migrations table.
    op.execute("DELETE FROM vector_migrations")

    # 3. Null out interest embeddings (384-dim, incompatible with new 1536-dim)
    op.execute("UPDATE user_interests SET embedding = NULL WHERE embedding IS NOT NULL")

    # 4. Null out interest notification embeddings (audit records, non-critical)
    op.execute(
        "UPDATE interest_notifications SET content_embedding = NULL "
        "WHERE content_embedding IS NOT NULL"
    )


def downgrade() -> None:
    """Downgrade is not automated.

    store_vectors is auto-managed by LangGraph — manual recreation not needed.
    Interest embeddings were nulled — recovery requires re-embedding with E5 model.
    """
    pass
