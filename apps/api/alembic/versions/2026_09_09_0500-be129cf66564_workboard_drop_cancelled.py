"""workboard: a ticket is closed by « Terminé », and by nothing else (ADR-276)

Revision ID: be129cf66564
Revises: 7c1e9a4d52b6
Create Date: 2026-09-09 05:00:00

« Annulé » is dropped on the owner's arbitration: a board is read ACROSS, and a
column that only ever holds abandoned work costs the same width as one that
holds live work. What was cancelled is finished — and the history already says
WHY, on the status event's ``reason``, which is where a motive belongs.

The rows move rather than being deleted: a cancelled ticket is a ticket the
person wrote, and the board's own « closed older than N days » filter already
hides it. ``status_changed_at`` is left alone on purpose — the ticket stopped
moving when it was cancelled, not when this migration ran, and that instant is
what the filter and the retention sweep read.

The downgrade cannot restore which of the closed tickets had been cancelled:
nothing records it once the value is gone. It is therefore a no-op that says so,
rather than a guess that would re-open finished work.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "be129cf66564"
down_revision = "7c1e9a4d52b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("UPDATE workboard_tickets SET status = 'done' WHERE status = 'cancelled'")
    )


def downgrade() -> None:
    """No-op: which tickets were cancelled is not recoverable (see the module docstring)."""
