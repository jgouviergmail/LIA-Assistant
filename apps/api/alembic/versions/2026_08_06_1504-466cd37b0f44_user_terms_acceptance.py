"""User terms-of-use acceptance (live-demonstrator programme, lot 2).

Two columns that always travel together: WHEN the user accepted, and WHICH
version they accepted. A consent with no version cannot be defended once the
terms change, so recording only the timestamp would be recording nothing.

Both are nullable: existing accounts were never asked, and a private instance
may never ask. NULL means "never asked", not "refused".

Revision ID: 466cd37b0f44
Revises: b665290a2fb4
Create Date: 2026-08-06 15:04:17.083898
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "466cd37b0f44"
down_revision: str | None = "b665290a2fb4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the terms-acceptance columns to users."""
    op.add_column(
        "users",
        sa.Column(
            "terms_accepted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the user accepted the terms of use. NULL = never asked.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "terms_version",
            sa.String(length=50),
            nullable=True,
            comment="Identifier of the terms version the user accepted.",
        ),
    )


def downgrade() -> None:
    """Drop the terms-acceptance columns."""
    op.drop_column("users", "terms_version")
    op.drop_column("users", "terms_accepted_at")
