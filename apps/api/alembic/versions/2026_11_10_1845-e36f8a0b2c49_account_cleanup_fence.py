"""Keep a retiring account inactive through external cleanup.

Revision ID: e36f8a0b2c49
Revises: d25e7f9a1b38
"""

from alembic import op
import sqlalchemy as sa

revision = "e36f8a0b2c49"
down_revision = "d25e7f9a1b38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add a content-free fence; existing accounts retain their current state."""
    op.add_column(
        "users", sa.Column("deletion_started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_users_deletion_inactive", "users", "deletion_started_at IS NULL OR NOT is_active"
    )


def downgrade() -> None:
    """Refuse to discard an unresolved account's reactivation fence."""
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM users WHERE deletion_started_at IS NOT NULL "
            "AND deleted_at IS NULL)"
        )
    ):
        raise RuntimeError("Resolve pending account cleanup before downgrade")
    op.drop_constraint("ck_users_deletion_inactive", "users", type_="check")
    op.drop_column("users", "deletion_started_at")
