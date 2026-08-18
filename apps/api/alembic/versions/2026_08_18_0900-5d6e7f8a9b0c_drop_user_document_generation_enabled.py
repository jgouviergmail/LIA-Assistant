"""Drop users.document_generation_enabled (owner decision 2026-08-18).

The per-user opt-in shipped with ADR-226 (v1.30.8) was judged not useful:
document generation is governed by the deployment flag and the admin platform
capability only. The column is removed rather than left dead (dead schema is
deleted, not kept "for later").

Revision ID: 5d6e7f8a9b0c
Revises: 4c5d6e7f8a9b
Create Date: 2026-08-18 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d6e7f8a9b0c"
down_revision: str | None = "4c5d6e7f8a9b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the per-user document generation opt-in column."""
    op.drop_column("users", "document_generation_enabled")


def downgrade() -> None:
    """Restore the column with its original definition."""
    op.add_column(
        "users",
        sa.Column(
            "document_generation_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="User opt-in for AI document generation feature.",
        ),
    )
