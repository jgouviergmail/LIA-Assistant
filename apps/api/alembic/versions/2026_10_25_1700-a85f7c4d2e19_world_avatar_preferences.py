"""Declared public world appearance, separate from private home colors.

Revision ID: a85f7c4d2e19
Revises: 4ea6258b83d2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a85f7c4d2e19"
down_revision: str | None = "4ea6258b83d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("world_avatar_preferences", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "world_avatar_preferences")
