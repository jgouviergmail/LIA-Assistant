"""Initial migration: users, connectors and embeddings tables

Revision ID: initial_001
Revises:
Create Date: 2025-01-15 00:01:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'initial_001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=True),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('oauth_provider', sa.String(length=50), nullable=True),
        sa.Column('oauth_provider_id', sa.String(length=255), nullable=True),
        sa.Column('picture_url', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_oauth_provider'), 'users', ['oauth_provider'], unique=False)

    # Create connectors table
    op.create_table(
        'connectors',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('connector_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('credentials_encrypted', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_connectors_user_id'), 'connectors', ['user_id'], unique=False)
    op.create_index(op.f('ix_connectors_connector_type'), 'connectors', ['connector_type'], unique=False)
    op.create_index(op.f('ix_connectors_status'), 'connectors', ['status'], unique=False)

    # Create embeddings table (for RAG/vector search)
    op.create_table(
        'embeddings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_embeddings_source'), 'embeddings', ['source'], unique=False)
    op.create_index(op.f('ix_embeddings_text'), 'embeddings', ['text'], unique=False, postgresql_using='gin', postgresql_ops={'text': 'gin_trgm_ops'})


def downgrade() -> None:
    op.drop_index(op.f('ix_embeddings_text'), table_name='embeddings')
    op.drop_index(op.f('ix_embeddings_source'), table_name='embeddings')
    op.drop_table('embeddings')
    op.drop_index(op.f('ix_connectors_status'), table_name='connectors')
    op.drop_index(op.f('ix_connectors_connector_type'), table_name='connectors')
    op.drop_index(op.f('ix_connectors_user_id'), table_name='connectors')
    op.drop_table('connectors')
    op.drop_index(op.f('ix_users_oauth_provider'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
