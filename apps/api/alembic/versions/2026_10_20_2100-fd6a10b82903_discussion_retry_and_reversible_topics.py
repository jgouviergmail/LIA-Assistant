"""Persist discretionary retry windows and reversible personal topic refusals.

Revision ID: fd6a10b82903
Revises: c409c74063f8
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "fd6a10b82903"
down_revision = "c409c74063f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discussion_runs", sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "discussion_preferences",
        sa.Column(
            "forbidden_topics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("discussion_preferences", "forbidden_topics")
    op.drop_column("discussion_runs", "retry_after")
