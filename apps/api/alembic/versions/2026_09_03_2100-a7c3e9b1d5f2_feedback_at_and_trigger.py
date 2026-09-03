"""Feedback timestamps and the notification trigger (ADR-214 amendment, ADR-261).

- ``heartbeat_notifications.feedback_at`` / ``interest_notifications.feedback_at``:
  WHEN the user gave a thumb. A thumb is an explicit human act and counts as
  reading presence for the rhythm detector (owner decision 2026-09-03); the
  historical ``user_feedback`` column only said WHAT, so rows before this
  migration stay silent — no backfill, there is no timestamp to backfill from.
- ``heartbeat_notifications.trigger``: ``tick`` (periodic runner) or ``push``
  (a Google push notification woke the decision, ADR-261). Server default
  ``tick`` keeps every existing row honest.

Both are additive and nullable/defaulted: safe on every deployment.

Revision ID: a7c3e9b1d5f2
Revises: e0f1a2b3c4d5
Create Date: 2026-09-03 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e9b1d5f2"
down_revision: str | None = "e0f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the feedback timestamps and the trigger column."""
    op.add_column(
        "heartbeat_notifications",
        sa.Column(
            "feedback_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the user gave feedback (presence source).",
        ),
    )
    op.add_column(
        "heartbeat_notifications",
        sa.Column(
            "trigger",
            sa.String(length=16),
            nullable=False,
            server_default="tick",
            comment="tick | push — what triggered this decision.",
        ),
    )
    op.add_column(
        "interest_notifications",
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Drop the three columns (symmetric)."""
    op.drop_column("interest_notifications", "feedback_at")
    op.drop_column("heartbeat_notifications", "trigger")
    op.drop_column("heartbeat_notifications", "feedback_at")
