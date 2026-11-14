"""Retain account filesystem writers through rollback and process interruption.

Revision ID: f4709b1c3d50
Revises: e36f8a0b2c49
"""

from alembic import op
import sqlalchemy as sa

revision = "f4709b1c3d50"
down_revision = "e36f8a0b2c49"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create content-free ownership, deliberately without a user CASCADE."""
    op.create_table(
        "account_file_writers",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_account_file_writers_owner", "account_file_writers", ["user_id"])
    op.create_index("ix_account_file_writers_boot", "account_file_writers", ["worker_id"])


def downgrade() -> None:
    """An unresolved writer is never discarded by rollback."""
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM account_file_writers)")):
        raise RuntimeError("Resolve account file writers before downgrade")
    op.drop_table("account_file_writers")
