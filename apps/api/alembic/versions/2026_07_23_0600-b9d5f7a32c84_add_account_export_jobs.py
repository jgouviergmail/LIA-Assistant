"""Add account_export_jobs (security program D3, GDPR portability).

Durable job bookkeeping for full-account exports: consumed by the interval
executor with FOR UPDATE SKIP LOCKED, at most one non-terminal job per user
(partial unique index). Archives live on disk and are bounded by
``expires_at`` (retention sweep).

Revision ID: b9d5f7a32c84
Revises: a8c4e6f21b73
Create Date: 2026-07-23 06:00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "b9d5f7a32c84"
down_revision = "a8c4e6f21b73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the account_export_jobs table."""
    op.create_table(
        "account_export_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
            comment="pending | running | done | failed | expired",
        ),
        sa.Column(
            "scope",
            JSONB,
            nullable=True,
            comment="Requested scope: {domains: [...]|null=all, from: iso|null, to: iso|null}.",
        ),
        sa.Column(
            "file_path",
            sa.Text(),
            nullable=True,
            comment="Absolute path of the built archive (set when DONE).",
        ),
        sa.Column(
            "file_size_bytes",
            sa.BigInteger(),
            nullable=True,
            comment="Archive size (set when DONE).",
        ),
        sa.Column(
            "error_code",
            sa.String(64),
            nullable=True,
            comment="Failure classification (export_too_large, build_failed, crashed…).",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Download deadline; the retention sweep purges past it.",
        ),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_account_export_jobs_user", "account_export_jobs", ["user_id"])
    op.create_index("ix_account_export_jobs_status", "account_export_jobs", ["status"])
    op.create_index(
        "uq_account_export_jobs_active_per_user",
        "account_export_jobs",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    """Drop the account_export_jobs table."""
    op.drop_index("uq_account_export_jobs_active_per_user", table_name="account_export_jobs")
    op.drop_index("ix_account_export_jobs_status", table_name="account_export_jobs")
    op.drop_index("ix_account_export_jobs_user", table_name="account_export_jobs")
    op.drop_table("account_export_jobs")
