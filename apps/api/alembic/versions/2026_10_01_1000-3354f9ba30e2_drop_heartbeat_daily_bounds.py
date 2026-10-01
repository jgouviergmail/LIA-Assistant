"""Drop the heartbeat's per-day bounds and its dead push preference (ADR-328).

Revision ID: 3354f9ba30e2
Revises: fc0147eeb095
Create Date: 2026-10-01 10:00:00.000000

The heartbeat no longer counts the day: the decision model judges whether a
signal is worth interrupting the person, the notification window and the
cooldowns bound how often, and a notification is never withheld because a
daily quota was reached. ``heartbeat_min_per_day`` and ``heartbeat_max_per_day``
therefore have no reader left.

``heartbeat_push_enabled`` goes with them: nothing has read it since
2026-08-05, when push started following the global notification opt-in alone,
and the settings panel never showed it again.

The downgrade restores the three columns with their former defaults (1, 3,
``true``), restated here as literals since a migration must not move when a
constant does. What each account had chosen is not restored: it is gone.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3354f9ba30e2"
down_revision: str | Sequence[str] | None = "fc0147eeb095"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DROPPED = ("heartbeat_min_per_day", "heartbeat_max_per_day", "heartbeat_push_enabled")


def upgrade() -> None:
    """Drop the per-day bounds and the unread push preference."""
    for column in _DROPPED:
        op.drop_column("users", column)


def downgrade() -> None:
    """Restore the three columns with their former defaults."""
    op.add_column(
        "users",
        sa.Column(
            "heartbeat_min_per_day",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Minimum heartbeat notifications per day (1-8).",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "heartbeat_max_per_day",
            sa.Integer(),
            nullable=False,
            server_default="3",
            comment="Maximum heartbeat notifications per day (1-8).",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "heartbeat_push_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Enable push (FCM/Telegram) for heartbeats. If false, only SSE + archive.",
        ),
    )
