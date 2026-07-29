"""Add users.chat_shortcuts (user-defined slash shortcuts).

UX Actions program, SLASH admin lot: one nullable JSONB column per feature
(same arbitration as briefing_preferences / onboarding_checklist). NULL means
"no user shortcuts"; the tolerant reader lives in domains/chat/shortcuts.

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-07-29 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable JSONB column — no backfill (NULL = no shortcuts)."""
    op.add_column(
        "users",
        sa.Column(
            "chat_shortcuts",
            JSONB,
            nullable=True,
            comment=(
                "User-defined chat slash shortcuts: [{id, text}, ...] — "
                "NULL = none (UX Actions program)."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the column — user shortcuts are a pure preference, safe to lose."""
    op.drop_column("users", "chat_shortcuts")
