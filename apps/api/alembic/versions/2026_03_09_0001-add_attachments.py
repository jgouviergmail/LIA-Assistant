"""Add attachments table for file uploads in chat.

Revision ID: add_attachments_001
Revises: llm_config_002
Create Date: 2026-03-09 00:01:00.000000

Phase: evolution F4 — File Attachments & Vision Analysis
Reference: docs/technical/ATTACHMENTS_INTEGRATION.md
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "add_attachments_001"
down_revision: str | None = "llm_config_002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            # Note: standalone user_id index omitted — covered by composite ix_attachments_user_id_created_at
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.Integer, nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(20), nullable=False),
        sa.Column("extracted_text", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="uploaded"),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            index=True,
        ),
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

    # Composite index for user queries (ownership + chronological order)
    op.create_index(
        "ix_attachments_user_id_created_at",
        "attachments",
        ["user_id", "created_at"],
    )

    # Index on status for cleanup queries
    op.create_index(
        "ix_attachments_status",
        "attachments",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_attachments_status", table_name="attachments")
    op.drop_index("ix_attachments_user_id_created_at", table_name="attachments")
    op.drop_table("attachments")
