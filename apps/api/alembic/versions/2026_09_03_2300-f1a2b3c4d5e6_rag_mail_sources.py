"""Add rag_mail_sources and the mail provenance columns of rag_documents (ADR-262).

Revision ID: f1a2b3c4d5e6
Revises: a7c3e9b1d5f2
Create Date: 2026-09-03

The mail source is an opt-in per Gmail label: the threads carrying the
label are rendered as Markdown documents of the space and follow the label.
Same durable-job columns as ``rag_drive_sources`` (lease, heartbeat,
attempts, worker) so the reaper recovers a crashed sync the same way, plus
the Gmail history id the incremental path (push-driven, ADR-261) resumes
from. ``rag_documents`` gains the thread identity and the newest message
stamp used for change detection.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "a7c3e9b1d5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create rag_mail_sources and add the mail columns to rag_documents."""
    op.create_table(
        "rag_mail_sources",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("space_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("label_id", sa.String(255), nullable=False),
        sa.Column("label_name", sa.String(500), nullable=False),
        sa.Column("sync_status", sa.String(20), nullable=False, server_default="idle"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("thread_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("synced_thread_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_history_id",
            sa.BigInteger(),
            nullable=True,
            comment="Gmail history id the incremental path resumes from (ADR-262)",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worker_id", sa.String(64), nullable=True),
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
        sa.ForeignKeyConstraint(["space_id"], ["rag_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rag_mail_sources_space_id", "rag_mail_sources", ["space_id"])
    op.create_index("ix_rag_mail_sources_user_id", "rag_mail_sources", ["user_id"])
    op.create_index(
        "uq_rag_mail_sources_space_label",
        "rag_mail_sources",
        ["space_id", "label_id"],
        unique=True,
    )
    op.create_index(
        "ix_rag_mail_sources_status_lease",
        "rag_mail_sources",
        ["sync_status", "lease_expires_at"],
    )

    op.add_column(
        "rag_documents",
        sa.Column("mail_source_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "rag_documents",
        sa.Column("mail_thread_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "rag_documents",
        sa.Column(
            "mail_last_message_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Newest message of the rendered thread (change detection)",
        ),
    )
    op.create_foreign_key(
        "fk_rag_documents_mail_source_id",
        "rag_documents",
        "rag_mail_sources",
        ["mail_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_rag_documents_mail_source_id", "rag_documents", ["mail_source_id"])
    op.create_index("ix_rag_documents_mail_thread_id", "rag_documents", ["mail_thread_id"])


def downgrade() -> None:
    """Drop the mail columns and the rag_mail_sources table."""
    op.drop_index("ix_rag_documents_mail_thread_id", table_name="rag_documents")
    op.drop_index("ix_rag_documents_mail_source_id", table_name="rag_documents")
    op.drop_constraint("fk_rag_documents_mail_source_id", "rag_documents", type_="foreignkey")
    op.drop_column("rag_documents", "mail_last_message_at")
    op.drop_column("rag_documents", "mail_thread_id")
    op.drop_column("rag_documents", "mail_source_id")

    op.drop_index("ix_rag_mail_sources_status_lease", table_name="rag_mail_sources")
    op.drop_index("uq_rag_mail_sources_space_label", table_name="rag_mail_sources")
    op.drop_index("ix_rag_mail_sources_user_id", table_name="rag_mail_sources")
    op.drop_index("ix_rag_mail_sources_space_id", table_name="rag_mail_sources")
    op.drop_table("rag_mail_sources")
