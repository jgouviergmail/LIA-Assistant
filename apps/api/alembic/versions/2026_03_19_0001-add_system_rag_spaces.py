"""Add system RAG spaces support.

Revision ID: system_rag_spaces_001
Revises: drive_sources_001
Create Date: 2026-03-19

Adds support for system RAG spaces (built-in knowledge bases like FAQ):
1. Makes user_id nullable on rag_spaces, rag_documents, rag_chunks
   (system spaces have no owner)
2. Adds is_system flag and content_hash to rag_spaces
3. Replaces the unique index on (user_id, name) with partial unique indexes:
   - User spaces: UNIQUE(user_id, name) WHERE user_id IS NOT NULL
   - System spaces: UNIQUE(name) WHERE is_system = true
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "system_rag_spaces_001"
down_revision: str | None = "drive_sources_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add system RAG spaces support."""
    # ---- 1. rag_spaces: Add is_system and content_hash columns ----
    op.add_column(
        "rag_spaces",
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="System spaces are built-in (FAQ, etc.) and cannot be modified by users",
        ),
    )
    op.add_column(
        "rag_spaces",
        sa.Column(
            "content_hash",
            sa.String(64),
            nullable=True,
            comment="SHA-256 hash of source content for staleness detection",
        ),
    )

    # ---- 2. rag_spaces: Make user_id nullable ----
    op.alter_column(
        "rag_spaces",
        "user_id",
        existing_type=sa.UUID(),
        nullable=True,
    )

    # ---- 3. rag_documents: Make user_id nullable ----
    op.alter_column(
        "rag_documents",
        "user_id",
        existing_type=sa.UUID(),
        nullable=True,
    )

    # ---- 4. rag_chunks: Make user_id nullable ----
    op.alter_column(
        "rag_chunks",
        "user_id",
        existing_type=sa.UUID(),
        nullable=True,
    )

    # ---- 5. Replace unique index with partial unique indexes ----
    # Drop the old unique index (user_id, name) — breaks when user_id is NULL
    op.drop_index("uq_rag_spaces_user_id_name", table_name="rag_spaces")

    # Partial unique index for user-owned spaces: unique name per user
    op.execute(
        "CREATE UNIQUE INDEX uq_rag_spaces_user_name "
        "ON rag_spaces (user_id, name) "
        "WHERE user_id IS NOT NULL"
    )

    # Partial unique index for system spaces: unique name globally
    op.execute(
        "CREATE UNIQUE INDEX uq_rag_spaces_system_name "
        "ON rag_spaces (name) "
        "WHERE is_system = true"
    )

    # ---- 6. Add index on is_system ----
    op.create_index("ix_rag_spaces_is_system", "rag_spaces", ["is_system"])


def downgrade() -> None:
    """Revert system RAG spaces support."""
    # ---- 6. Drop is_system index ----
    op.drop_index("ix_rag_spaces_is_system", table_name="rag_spaces")

    # ---- 5. Restore original unique index ----
    op.execute("DROP INDEX IF EXISTS uq_rag_spaces_system_name")
    op.execute("DROP INDEX IF EXISTS uq_rag_spaces_user_name")

    # Delete any system spaces before restoring NOT NULL constraint
    op.execute("DELETE FROM rag_spaces WHERE is_system = true")

    op.create_index(
        "uq_rag_spaces_user_id_name",
        "rag_spaces",
        ["user_id", "name"],
        unique=True,
    )

    # ---- 4. rag_chunks: Restore NOT NULL on user_id ----
    op.execute("DELETE FROM rag_chunks WHERE user_id IS NULL")
    op.alter_column(
        "rag_chunks",
        "user_id",
        existing_type=sa.UUID(),
        nullable=False,
    )

    # ---- 3. rag_documents: Restore NOT NULL on user_id ----
    op.execute("DELETE FROM rag_documents WHERE user_id IS NULL")
    op.alter_column(
        "rag_documents",
        "user_id",
        existing_type=sa.UUID(),
        nullable=False,
    )

    # ---- 2. rag_spaces: Restore NOT NULL on user_id ----
    op.alter_column(
        "rag_spaces",
        "user_id",
        existing_type=sa.UUID(),
        nullable=False,
    )

    # ---- 1. Drop new columns ----
    op.drop_column("rag_spaces", "content_hash")
    op.drop_column("rag_spaces", "is_system")
