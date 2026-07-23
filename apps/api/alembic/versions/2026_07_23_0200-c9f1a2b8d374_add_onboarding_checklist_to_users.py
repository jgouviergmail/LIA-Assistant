"""Add users.onboarding_checklist (UXR Lot 6, A10).

Persistence of the "getting started" checklist card state: dismissal and
celebration timestamps only — item states are DETECTED live, never stored.
Nullable JSONB; NULL = card eligible (subject to the completion rules).
Writes are full NEW-dict replacements (JSONB new-dict rule).

Revision ID: c9f1a2b8d374
Revises: b7e3d9c41a56
Create Date: 2026-07-23 02:00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision = "c9f1a2b8d374"
down_revision = "b7e3d9c41a56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable JSONB checklist-state column."""
    op.add_column(
        "users",
        sa.Column(
            "onboarding_checklist",
            JSONB,
            nullable=True,
            comment=(
                "Starter checklist card state: {dismissed_at, celebrated_at} "
                "ISO-UTC — item states are detected live, never stored (UXR A10)."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the checklist-state column."""
    op.drop_column("users", "onboarding_checklist")
