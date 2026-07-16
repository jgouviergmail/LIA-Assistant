"""RAG durable jobs: lease/heartbeat/attempts on documents + drive sources (F001)

Revision ID: 9a1c4e7f2b8d
Revises: d3f1a9c40b52
Create Date: 2026-07-14 14:30:00.000000

Adds the durable-job columns (audit F001, Phase 1) that turn RAGDocument and
RAGDriveSource into leased, resumable jobs, plus composite indexes serving the
recovery reaper's ``(status, lease_expires_at)`` scan. All new columns are
nullable / defaulted, so the migration is non-blocking on existing rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a1c4e7f2b8d"
down_revision: str | None = "d3f1a9c40b52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("rag_documents", "rag_drive_sources")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        )
        op.add_column(
            table,
            sa.Column("worker_id", sa.String(length=64), nullable=True),
        )

    # Reaper scan indexes: each table's status column + lease expiry.
    op.create_index(
        "ix_rag_documents_status_lease",
        "rag_documents",
        ["status", "lease_expires_at"],
    )
    op.create_index(
        "ix_rag_drive_sources_status_lease",
        "rag_drive_sources",
        ["sync_status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_rag_drive_sources_status_lease", table_name="rag_drive_sources")
    op.drop_index("ix_rag_documents_status_lease", table_name="rag_documents")
    for table in _TABLES:
        op.drop_column(table, "worker_id")
        op.drop_column(table, "attempts")
        op.drop_column(table, "heartbeat_at")
        op.drop_column(table, "lease_expires_at")
