"""The stale-relay sweep's index (phone-as-a-channel, lot 4).

An owner call's return is relayed as the person's own chat turn; while that
runs the outbox row is ``RELAYING``, and a crash mid-relay would leave it so
forever. The sweep flips such rows to ``PENDING`` past a max age, and scans
only them: a partial index on the completion time, like the reaper's own.
``native_enum=False`` stores the member NAME, so the predicate matches
``'RELAYING'`` uppercase.

Revision ID: b3c8e0f2d4a6
Revises: a2b7d9f1c3e5
Create Date: 2026-09-16 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c8e0f2d4a6"
down_revision: str | None = "a2b7d9f1c3e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the partial index the stale-relay sweep scans."""
    op.create_index(
        "ix_phone_calls_notification_relaying",
        "phone_calls",
        ["completed_at"],
        unique=False,
        postgresql_where=sa.text("notification_status = 'RELAYING'"),
    )


def downgrade() -> None:
    """Drop the partial index."""
    op.drop_index("ix_phone_calls_notification_relaying", table_name="phone_calls")
