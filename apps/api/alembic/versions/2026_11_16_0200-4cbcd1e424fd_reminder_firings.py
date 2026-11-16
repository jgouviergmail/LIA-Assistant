"""Reminder firings: the occurrence a snooze names (ADR-268 amendment 2026-11-16).

Revision ID: 4cbcd1e424fd
Revises: b7b4b7c9dd28
Create Date: 2026-11-16 02:00:00.000000

One row per reminder occurrence that rang, kept while it can be postponed and
purged after the window. A press names this row, never the reminder: a one-shot
reminder is deleted the instant it fires, and a series has already moved on.

``reminders.first_asked_at`` is set only on the one-shot copy a snooze creates:
when the person first asked, carried across the postponement.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "4cbcd1e424fd"
down_revision: str | None = "b7b4b7c9dd28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the firings table and the postponed copy's memory of the request."""
    op.add_column(
        "reminders",
        sa.Column(
            "first_asked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the person first asked; set only on a copy a snooze created.",
        ),
    )
    op.create_table(
        "reminder_firings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reminder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reminders.id", ondelete="SET NULL"),
            nullable=True,
            comment=(
                "The reminder that rang, while it exists: a series, or a one-shot "
                "not yet deleted."
            ),
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            comment="What rang, copied: the reminder may already be gone.",
        ),
        sa.Column(
            "original_message",
            sa.Text(),
            nullable=False,
            comment="The person's own request, copied for the postponed copy's message.",
        ),
        sa.Column(
            "asked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the person first asked for it (carried to a postponed copy).",
        ),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When it rang; the snooze window and the purge count from it.",
        ),
        sa.Column(
            "snoozed_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="The instant it was postponed to; NULL while it was not.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reminder_firings_user_id", "reminder_firings", ["user_id"])
    op.create_index("ix_reminder_firings_reminder_id", "reminder_firings", ["reminder_id"])
    op.create_index("ix_reminder_firings_fired_at", "reminder_firings", ["fired_at"])


def downgrade() -> None:
    """Drop the firings table and the column."""
    op.drop_index("ix_reminder_firings_fired_at", table_name="reminder_firings")
    op.drop_index("ix_reminder_firings_reminder_id", table_name="reminder_firings")
    op.drop_index("ix_reminder_firings_user_id", table_name="reminder_firings")
    op.drop_table("reminder_firings")
    op.drop_column("reminders", "first_asked_at")
