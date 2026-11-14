"""Retain a confirmed file's identity through physical-cleanup retries.

Revision ID: c14d6e8f0a27
Revises: b03c5d7e9f16
"""

from alembic import op
import sqlalchemy as sa

revision = "c14d6e8f0a27"
down_revision = "b03c5d7e9f16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """An unbound witness preserves legacy semantics; confirmed acts fill both fields."""
    op.add_column(
        "attachments",
        sa.Column(
            "deletion_check_identity", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "attachments", sa.Column("deletion_expected_digest", sa.String(64), nullable=True)
    )


def downgrade() -> None:
    """Never discard the witness of an unfinished confirmed removal."""
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM attachments WHERE deletion_check_identity)")
    ):
        raise RuntimeError("Cannot discard pending attachment deletion identity")
    op.drop_column("attachments", "deletion_expected_digest")
    op.drop_column("attachments", "deletion_check_identity")
