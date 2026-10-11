"""Fence background learning after explicit consent changes.

Revision ID: f19c83e2a6b0
Revises: c29fba860e13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f19c83e2a6b0"
down_revision: str | None = "c29fba860e13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("extraction_revision", sa.BigInteger(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "extraction_revision")
