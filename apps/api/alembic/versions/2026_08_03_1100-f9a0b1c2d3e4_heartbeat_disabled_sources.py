"""heartbeat: sources the user refuses to be interrupted from

Being connected to a service and being interrupted from it were the same
switch: the only documented way to stop mail-driven nudges was to disconnect
the mail connector, which also removes the tool the user asks with.

Stored as the REFUSAL set, not the allowlist. NULL therefore means "never
expressed a preference", so every existing account keeps its exact behaviour
without a data migration, and a source added to the registry later is on until
the user refuses it — rather than silently missing from everyone's stored
allowlist.

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-08-03 11:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "f9a0b1c2d3e4"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "heartbeat_disabled_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Heartbeat sources the user refused; NULL = all enabled.",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "heartbeat_disabled_sources")
