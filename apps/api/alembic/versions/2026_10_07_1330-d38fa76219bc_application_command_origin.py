"""Persist optional encrypted transport identity without granting stored authority.

Revision ID: d38fa76219bc
Revises: a92d4e713b60
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d38fa76219bc"
down_revision: str | None = "a92d4e713b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application_commands", sa.Column("origin_binding_encrypted", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("application_commands", "origin_binding_encrypted")
