"""Keep attachment disk writers and removal claims durably owned.

Revision ID: b03c5d7e9f16
Revises: a92b4c6d8e05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b03c5d7e9f16"
down_revision: str | Sequence[str] | None = "a92b4c6d8e05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Preserve existing files; only future I/O owns a token and boot identity."""
    op.add_column("attachments", sa.Column("io_worker_id", sa.Uuid(), nullable=True))
    op.add_column("attachments", sa.Column("io_owner_token", sa.Uuid(), nullable=True))
    op.add_column(
        "attachments", sa.Column("io_fence", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "attachments", sa.Column("io_claimed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint("ck_attachments_io_fence", "attachments", "io_fence >= 0")
    op.create_index("ix_attachments_io_worker", "attachments", ["io_worker_id"])


def downgrade() -> None:
    """Unknown writers and pending removals must finish before their authority is removed."""
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM attachments "
            "WHERE io_owner_token IS NOT NULL OR status='deleting')"
        )
    ):
        raise RuntimeError("Cannot remove attachment I/O authority while work is unfinished")
    op.drop_index("ix_attachments_io_worker", table_name="attachments")
    op.drop_constraint("ck_attachments_io_fence", "attachments", type_="check")
    for column in ("io_claimed_at", "io_fence", "io_owner_token", "io_worker_id"):
        op.drop_column("attachments", column)
