"""Complete transport authority on databases that ran an early development revision.

Revision ID: d69e1f3a5b72
Revises: c58d9e2f4a61

Development restarted while c58 was being implemented and recorded its earlier
shape without cancellable or the owner/stream index. A new revision is needed:
rerunning upgrade head cannot detect an edited already-recorded migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d69e1f3a5b72"
down_revision: str | Sequence[str] | None = "c58d9e2f4a61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make the early and complete development shapes converge without losing rows."""
    op.execute(
        sa.text(
            "ALTER TABLE conversation_executions "
            "ADD COLUMN IF NOT EXISTS cancellable boolean NOT NULL DEFAULT false"
        )
    )
    # Existing invocations were not cancellable. Future ones explicitly declare
    # the fact, exactly as the canonical parent and the ORM model require.
    op.execute(sa.text("ALTER TABLE conversation_executions ALTER COLUMN cancellable DROP DEFAULT"))
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_execution_owner_stream "
            "ON conversation_executions (user_id, stream_id)"
        )
    )


def downgrade() -> None:
    """Retain fields already declared by the canonical parent migration."""
