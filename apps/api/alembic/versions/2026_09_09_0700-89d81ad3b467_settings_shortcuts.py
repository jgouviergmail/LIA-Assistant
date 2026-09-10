"""Add users.settings_shortcuts (pinned settings sections, ADR-277).

One nullable JSONB column per feature — the arbitration `chat_shortcuts` and
`briefing_preferences` already follow. NULL means "nothing pinned"; the
tolerant reader lives in domains/shared/settings_shortcuts.

Revision ID: 89d81ad3b467
Revises: 313ab021caa4
Create Date: 2026-09-09 07:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "89d81ad3b467"
down_revision: str | None = "313ab021caa4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable JSONB column — no backfill (NULL = nothing pinned)."""
    op.add_column(
        "users",
        sa.Column(
            "settings_shortcuts",
            JSONB,
            nullable=True,
            comment=(
                "Settings section tokens pinned to the floating shortcuts dock: "
                "[token, ...] — NULL = none (ADR-277)."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the column — a pinned list is a pure preference, safe to lose."""
    op.drop_column("users", "settings_shortcuts")
