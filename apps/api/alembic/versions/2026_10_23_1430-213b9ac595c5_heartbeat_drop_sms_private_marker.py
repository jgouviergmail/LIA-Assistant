"""Drop the SMS private marker of heartbeat notifications (ADR-357 amendment 2026-10-23).

The column marked every notification written while an SMS sat in the decision's
context, and the marked rows were withheld from the next decision's
anti-repetition window. An SMS stays in view for its whole summary window, so nearly
every notification of an account that receives SMS was withheld, and the same subject
came back at every tick (one birthday announced six times between 21:07 and 13:29
the next day, measured in production on 2026-10-23). An SMS is now personal data
like a mail: nothing reads or writes the marker any more.

Dropping a column rewrites no row. The downgrade restores it unmarked: which
past rows had an SMS in view is not recoverable, and an unmarked row is what
every reader before this revision treated as ordinary.

Revision ID: 213b9ac595c5
Revises: 6b7fe9493921
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "213b9ac595c5"
down_revision: str | None = "6b7fe9493921"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("heartbeat_notifications", "sensitive_context")


def downgrade() -> None:
    op.add_column(
        "heartbeat_notifications",
        sa.Column("sensitive_context", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
