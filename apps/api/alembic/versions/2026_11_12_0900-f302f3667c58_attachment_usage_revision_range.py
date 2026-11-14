"""Give a file use the revision range of the discussion it names.

Revision ID: f302f3667c58
Revises: 27fc835b8d44

``conversations.revision`` is a BIGINT, and so is every other copy of it
(executions, operations). ``conversation_attachment_usages.conversation_revision``
was created as an INTEGER by ``a92b4c6d8e05``: a narrower copy of the same
number. A new revision is needed because that migration already ran where this
lot was developed; rerunning ``upgrade head`` cannot see an edited one.

The table is rewritten under its exclusive lock. It holds one row per file a
discussion accepted, so the rewrite is short.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f302f3667c58"
down_revision: str | Sequence[str] | None = "27fc835b8d44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "conversation_attachment_usages"
_COLUMN = "conversation_revision"


def upgrade() -> None:
    """Widen the copy; every stored value fits and none is changed."""
    op.alter_column(
        _TABLE,
        _COLUMN,
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Narrow it back; PostgreSQL refuses, rather than truncates, a value out of range."""
    op.alter_column(
        _TABLE,
        _COLUMN,
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
