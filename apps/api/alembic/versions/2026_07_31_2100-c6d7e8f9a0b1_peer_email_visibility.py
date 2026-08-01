"""peer email visibility opt-in

Being findable and handing your address over are two different consents
(ADR-189), so this is its own column rather than a second meaning attached to
``discovery_enabled``. Default OFF, like every peers opt-in: the address is
only ever shown to ACCEPTED connections, and only if its owner asked for it.

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-07-31 21:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the opt-in, off for everyone who already exists."""
    op.add_column(
        "users",
        sa.Column(
            "peer_email_visible",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Opt-in: accepted connections see this user's real email. Default off.",
        ),
    )


def downgrade() -> None:
    """Drop the opt-in (addresses go back to being masked for everyone)."""
    op.drop_column("users", "peer_email_visible")
