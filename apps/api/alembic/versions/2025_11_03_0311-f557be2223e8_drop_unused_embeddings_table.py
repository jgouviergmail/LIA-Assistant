"""drop_unused_embeddings_table

Revision ID: f557be2223e8
Revises: user_timezone_001
Create Date: 2025-11-03 03:11:05.919966

Cleanup: Remove unused embeddings table and vector store infrastructure.
The embeddings table was created for RAG/vector search functionality but
was never used in production. Corresponding code (vector_store.py) has been removed.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f557be2223e8'
down_revision: str | None = 'user_timezone_001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop indexes first
    op.drop_index(op.f('ix_embeddings_text'), table_name='embeddings')
    op.drop_index(op.f('ix_embeddings_source'), table_name='embeddings')

    # Drop the embeddings table
    op.drop_table('embeddings')


def downgrade() -> None:
    # Recreate embeddings table (for rollback capability)
    op.create_table(
        'embeddings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Recreate indexes
    op.create_index(op.f('ix_embeddings_source'), 'embeddings', ['source'], unique=False)
    op.create_index(
        op.f('ix_embeddings_text'),
        'embeddings',
        ['text'],
        unique=False,
        postgresql_using='gin',
        postgresql_ops={'text': 'gin_trgm_ops'}
    )
