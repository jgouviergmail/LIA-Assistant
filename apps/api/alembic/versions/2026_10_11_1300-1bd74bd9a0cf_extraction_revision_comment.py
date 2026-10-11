"""Document users.extraction_revision in the schema, as the model already does.

Revision ID: 1bd74bd9a0cf
Revises: 36ecac9a51ea
Create Date: 2026-10-11 13:00:00.000000

Migration f19c83e2a6b0 added the column without the comment the model
declares, and column comments are part of the schema contract (audit F042):
the from-scratch replay check reported it as structural drift.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1bd74bd9a0cf"
down_revision: str | Sequence[str] | None = "36ecac9a51ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = "Fences background learning after explicit consent or personal-data management changes."


def upgrade() -> None:
    """Give the column the comment its model declares."""
    op.alter_column(
        "users",
        "extraction_revision",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
        comment=_COMMENT,
        existing_comment=None,
    )


def downgrade() -> None:
    """Remove the column comment again."""
    op.alter_column(
        "users",
        "extraction_revision",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
        comment=None,
        existing_comment=_COMMENT,
    )
