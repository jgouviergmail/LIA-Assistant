"""Owner world catalogue preferences, without duplicated personal source content.

Revision ID: c36cda5a9b71
Revises: 213b9ac595c5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c36cda5a9b71"
down_revision: str | None = "213b9ac595c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("world_preferences", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "world_preferences")
