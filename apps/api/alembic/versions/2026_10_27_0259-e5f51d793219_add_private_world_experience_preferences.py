"""add private world experience preferences

Revision ID: e5f51d793219
Revises: e9c014ab7f62
Create Date: 2026-10-27 02:59:17.288966

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5f51d793219"
down_revision: str = "e9c014ab7f62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a nullable independent document; existing owners retain runtime defaults."""
    op.add_column(
        "users", sa.Column("world_experience_preferences", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    """Remove only this lot's private presentation document."""
    op.drop_column("users", "world_experience_preferences")
