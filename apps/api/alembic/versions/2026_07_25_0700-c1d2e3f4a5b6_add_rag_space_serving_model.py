"""Add rag_spaces.serving_embedding_model (generational RAG continuity, AC-001).

Durable per-space pointer to the embedding-model generation that retrieval must
embed queries with AND filter chunks to. NULL (the default and steady state)
means "single generation — serve every chunk", so existing rows keep their
current behaviour without a backfill. During a same-dimension reindex the
pointer is pinned to the OLD model while the NEW generation is built side by
side, then flipped atomically per space (search stays continuous on the stable
generation, never a mix or an empty window).

Additive and reversible: a nullable column with no server default and no data
migration.

Revision ID: c1d2e3f4a5b6
Revises: b9d5f7a32c84
Create Date: 2026-07-25 07:00:00
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c1d2e3f4a5b6"
down_revision = "b9d5f7a32c84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable serving_embedding_model column to rag_spaces."""
    op.add_column(
        "rag_spaces",
        sa.Column(
            "serving_embedding_model",
            sa.String(length=100),
            nullable=True,
            comment=(
                "Generational RAG continuity (AC-001): the embedding-model generation "
                "that retrieval must embed queries with AND filter chunks to for this "
                "space. NULL = single generation, serve every chunk (steady state). "
                "During a same-dimension reindex it is pinned to the OLD model so the "
                "stable generation stays fully readable while the NEW generation is "
                "built side by side, then flipped atomically per space."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the serving_embedding_model column."""
    op.drop_column("rag_spaces", "serving_embedding_model")
