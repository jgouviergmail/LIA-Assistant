"""Index history's complete order and the newest answer of each billed run.

Revision ID: f81a3b5c7d94
Revises: e70f2a4b6c83
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f81a3b5c7d94"
down_revision: str | Sequence[str] | None = "e70f2a4b6c83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "conversation_messages"
_HISTORY = "ix_conversation_messages_history_position"
_RUN = "ix_conversation_messages_run_position"
_OLD = "ix_conversation_messages_conv_created"


def upgrade() -> None:
    """Build the replacement before removing the prefix-only index; preserve all rows."""
    op.create_index(_HISTORY, _TABLE, ["conversation_id", "created_at", "id"])
    op.create_index(
        _RUN,
        _TABLE,
        ["conversation_id", sa.text("(message_metadata ->> 'run_id')"), "created_at", "id"],
    )
    op.drop_index(_OLD, table_name=_TABLE)


def downgrade() -> None:
    """Restore the old ordering without changing any history or accounting record."""
    op.create_index(_OLD, _TABLE, ["conversation_id", sa.text("created_at DESC")])
    op.drop_index(_RUN, table_name=_TABLE)
    op.drop_index(_HISTORY, table_name=_TABLE)
