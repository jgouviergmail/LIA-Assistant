"""add subject to user_interests

Subject label for thematic grouping of interest notifications (ADR-131).
Nullable by design: NULL means "needs clustering" and is the stale marker
consumed by the batch subject-clustering scheduler job.

Revision ID: 0ef84488b15c
Revises: 9a1c4e7f2b8d
Create Date: 2026-07-18 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0ef84488b15c"
down_revision = "9a1c4e7f2b8d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable subject label column (ADR-131). NULL = needs clustering."""
    op.add_column(
        "user_interests",
        sa.Column("subject", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    """Drop the subject label column."""
    op.drop_column("user_interests", "subject")
