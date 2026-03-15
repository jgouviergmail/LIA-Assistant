"""Add RAG Spaces tables for user knowledge document management.

Creates three tables:
- rag_spaces: User-owned knowledge spaces
- rag_documents: Uploaded documents within spaces
- rag_chunks: Vector-indexed text chunks with pgvector embeddings

Revision ID: rag_spaces_001
Revises: skills_002
Create Date: 2026-03-14 00:01:00.000000

Phase: evolution — RAG Spaces (User Knowledge Documents)
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "rag_spaces_001"
down_revision: str | None = "skills_002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Ensure pgvector extension is available
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- rag_spaces ---
    op.create_table(
        "rag_spaces",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_rag_spaces_user_id_is_active",
        "rag_spaces",
        ["user_id", "is_active"],
    )
    op.create_index(
        "uq_rag_spaces_user_id_name",
        "rag_spaces",
        ["user_id", "name"],
        unique=True,
    )

    # --- rag_documents ---
    op.create_table(
        "rag_documents",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "space_id",
            UUID(as_uuid=True),
            sa.ForeignKey("rag_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_size", sa.Integer, nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'processing'")),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_rag_documents_space_id_status",
        "rag_documents",
        ["space_id", "status"],
    )
    op.create_index(
        "ix_rag_documents_user_id",
        "rag_documents",
        ["user_id"],
    )

    # --- rag_chunks ---
    op.create_table(
        "rag_chunks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("rag_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "space_id",
            UUID(as_uuid=True),
            sa.ForeignKey("rag_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_rag_chunks_document_id", "rag_chunks", ["document_id"])
    op.create_index("ix_rag_chunks_space_id", "rag_chunks", ["space_id"])
    op.create_index("ix_rag_chunks_user_id_space_id", "rag_chunks", ["user_id", "space_id"])

    # HNSW index for cosine similarity search on embeddings
    op.execute(
        "CREATE INDEX ix_rag_chunks_embedding ON rag_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_rag_chunks_embedding")
    op.drop_index("ix_rag_chunks_user_id_space_id", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_space_id", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_document_id", table_name="rag_chunks")
    op.drop_table("rag_chunks")

    op.drop_index("ix_rag_documents_user_id", table_name="rag_documents")
    op.drop_index("ix_rag_documents_space_id_status", table_name="rag_documents")
    op.drop_table("rag_documents")

    op.drop_index("uq_rag_spaces_user_id_name", table_name="rag_spaces")
    op.drop_index("ix_rag_spaces_user_id_is_active", table_name="rag_spaces")
    op.drop_table("rag_spaces")
