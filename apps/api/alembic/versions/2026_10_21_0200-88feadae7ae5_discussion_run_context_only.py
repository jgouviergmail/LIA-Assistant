"""Tell a context rebuild apart from an opening run.

The settings page shows a rebuild in progress, then what the last one cost; a
run row that does not say which kind it was cannot answer either question.

Revision ID: 88feadae7ae5
Revises: 2c7e893a6d10
"""

from alembic import op
import sqlalchemy as sa

revision = "88feadae7ae5"
down_revision = "2c7e893a6d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discussion_runs",
        sa.Column("context_only", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index(
        "ix_discussion_runs_owner_rebuilds",
        "discussion_runs",
        ["user_id", "claimed_at"],
        postgresql_where=sa.text("context_only"),
    )


def downgrade() -> None:
    op.drop_index("ix_discussion_runs_owner_rebuilds", table_name="discussion_runs")
    op.drop_column("discussion_runs", "context_only")
