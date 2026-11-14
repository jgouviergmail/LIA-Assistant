"""Let a routine hold its notification back when a run found nothing new.

Revision ID: b6e2f48a1c93
Revises: 7a3c9e51d4b8

A routine notified its owner at every run, whether or not the run had anything
to say: a monitoring routine answered « nothing to report » on a phone every
morning. ``notify_only_when_new`` is the routine's own option: the run still
happens and its answer still lands in the chat, and the notification is held
back when the answering model declares it found nothing new (ADR-265 amendment
2026-11-12 c). False for every existing routine — a metadata-only change on
PostgreSQL, no table rewrite.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6e2f48a1c93"
down_revision: str | Sequence[str] | None = "7a3c9e51d4b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "scheduled_actions"
_COLUMN = "notify_only_when_new"


def upgrade() -> None:
    """Add the option, off for every routine that exists."""
    op.add_column(
        _TABLE,
        sa.Column(
            _COLUMN,
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment="True = a run that found nothing new is answered in the chat and not notified.",
        ),
    )


def downgrade() -> None:
    """Drop the option: every routine notifies at every run again."""
    op.drop_column(_TABLE, _COLUMN)
