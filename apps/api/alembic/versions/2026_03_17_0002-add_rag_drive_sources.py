"""Add rag_drive_sources table and Drive sync columns to rag_documents.

Revision ID: drive_sources_001
Revises: skills_tables_001
Create Date: 2026-03-17

Adds support for Google Drive folder sync in RAG Spaces:
1. Creates the rag_drive_sources table (linked Drive folders per space)
2. Adds source_type, drive_source_id, drive_file_id, drive_modified_time
   columns to rag_documents for tracking Drive-originated documents
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "drive_sources_001"
down_revision: str | None = "skills_tables_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create rag_drive_sources table and add Drive columns to rag_documents."""
    # ---- 1. Create rag_drive_sources table ----
    op.create_table(
        "rag_drive_sources",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("space_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("folder_id", sa.String(255), nullable=False),
        sa.Column("folder_name", sa.String(500), nullable=False),
        sa.Column(
            "sync_status",
            sa.String(20),
            nullable=False,
            server_default="idle",
        ),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_count", sa.Integer(), server_default="0"),
        sa.Column("synced_file_count", sa.Integer(), server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["space_id"], ["rag_spaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rag_drive_sources_space_id",
        "rag_drive_sources",
        ["space_id"],
    )
    op.create_index(
        "ix_rag_drive_sources_user_id",
        "rag_drive_sources",
        ["user_id"],
    )
    op.create_index(
        "uq_rag_drive_sources_space_folder",
        "rag_drive_sources",
        ["space_id", "folder_id"],
        unique=True,
    )

    # ---- 2. Add Drive columns to rag_documents ----
    op.add_column(
        "rag_documents",
        sa.Column(
            "source_type",
            sa.String(20),
            nullable=False,
            server_default="upload",
        ),
    )
    op.add_column(
        "rag_documents",
        sa.Column(
            "drive_source_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "rag_documents",
        sa.Column(
            "drive_file_id",
            sa.String(255),
            nullable=True,
        ),
    )
    op.add_column(
        "rag_documents",
        sa.Column(
            "drive_modified_time",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Foreign key for drive_source_id
    op.create_foreign_key(
        "fk_rag_documents_drive_source_id",
        "rag_documents",
        "rag_drive_sources",
        ["drive_source_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Indexes on new columns
    op.create_index(
        "ix_rag_documents_drive_source_id",
        "rag_documents",
        ["drive_source_id"],
    )
    op.create_index(
        "ix_rag_documents_drive_file_id",
        "rag_documents",
        ["drive_file_id"],
    )


def downgrade() -> None:
    """Remove Drive columns from rag_documents and drop rag_drive_sources."""
    # ---- 1. Drop indexes and columns from rag_documents ----
    op.drop_index("ix_rag_documents_drive_file_id", table_name="rag_documents")
    op.drop_index("ix_rag_documents_drive_source_id", table_name="rag_documents")
    op.drop_constraint(
        "fk_rag_documents_drive_source_id",
        "rag_documents",
        type_="foreignkey",
    )
    op.drop_column("rag_documents", "drive_modified_time")
    op.drop_column("rag_documents", "drive_file_id")
    op.drop_column("rag_documents", "drive_source_id")
    op.drop_column("rag_documents", "source_type")

    # ---- 2. Drop rag_drive_sources table ----
    op.drop_index(
        "uq_rag_drive_sources_space_folder",
        table_name="rag_drive_sources",
    )
    op.drop_index(
        "ix_rag_drive_sources_user_id",
        table_name="rag_drive_sources",
    )
    op.drop_index(
        "ix_rag_drive_sources_space_id",
        table_name="rag_drive_sources",
    )
    op.drop_table("rag_drive_sources")
