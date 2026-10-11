"""Give each routine execution reservation an opaque identity.

Revision ID: e47c0a52d9f1
Revises: d38fa76219bc
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e47c0a52d9f1"
down_revision: str | None = "d38fa76219bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scheduled_actions",
        sa.Column(
            "execution_token",
            sa.Uuid(),
            nullable=True,
            comment="Opaque reservation identity; a late manual job cannot consume a newer run.",
        ),
    )


def downgrade() -> None:
    op.drop_column("scheduled_actions", "execution_token")
