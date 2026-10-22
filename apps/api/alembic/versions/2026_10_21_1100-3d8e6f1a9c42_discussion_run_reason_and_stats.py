"""Say why a discussion run ended, and what it read and interpreted.

A rebuild that read nineteen sources and interpreted nothing used to settle as
``completed``: the run row kept no reason and no count, so neither the settings page
nor an operator could tell an empty context from a built one. ``reason`` holds the
run's closed outcome vocabulary (``RunReason``), ``stats`` its counts — never content.

Revision ID: 3d8e6f1a9c42
Revises: 88feadae7ae5
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "3d8e6f1a9c42"
down_revision = "88feadae7ae5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("discussion_runs", sa.Column("reason", sa.String(length=48), nullable=True))
    op.add_column(
        "discussion_runs",
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discussion_runs", "stats")
    op.drop_column("discussion_runs", "reason")
