"""relation overview scope

What a "360° point" is allowed to read. Stored server-side so the reader's
selection is a GUARANTEE rather than a hint: the chat link carries prose, and
the tool reads this instead of inferring the scope from a sentence.

NULL means "defaults" — everything, five items each. A row is only written
once the user changes something, so the column stays empty for people who
never open the panel.

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-08-01 09:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "d7e8f9a0b1c2"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the scope column (nullable — absence means defaults)."""
    op.add_column(
        "users",
        sa.Column(
            "relation_overview_scope",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Sections/directions/roles/max the 360° chat tool applies. Null = defaults."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the scope (every 360° goes back to reading everything)."""
    op.drop_column("users", "relation_overview_scope")
