"""Keep body-free read-rule and readiness checkpoints.

Revision ID: 1b8d4f925a10
Revises: fd6a10b82903
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "1b8d4f925a10"
down_revision = "fd6a10b82903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("rule_cache", "ready_context"):
        op.add_column(
            "discussion_context_states", sa.Column(name, postgresql.JSONB(), nullable=True)
        )


def downgrade() -> None:
    for name in ("ready_context", "rule_cache"):
        op.drop_column("discussion_context_states", name)
