"""Add users.document_generation_enabled (ADR-226).

Per-user opt-in for the AI document generation feature (generate_document
tool). Additive with ``server_default="true"``: existing rows keep the
feature enabled, mirroring ``image_generation_enabled``.

Revision ID: 4c5d6e7f8a9b
Revises: 3b4c5d6e7f8a
Create Date: 2026-08-17 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c5d6e7f8a9b"
down_revision: str | None = "3b4c5d6e7f8a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the per-user document generation opt-in column."""
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


def downgrade() -> None:
    """Drop the per-user document generation opt-in column."""
    op.drop_column("users", "document_generation_enabled")
