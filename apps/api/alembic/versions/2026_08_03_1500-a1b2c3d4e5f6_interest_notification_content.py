"""interests: keep the message that was sent, not only its hash

`interest_notifications` was built for deduplication and stored a SHA-256 hash
plus an embedding. The settings panel could therefore show WHEN LIA interrupted
the reader and never WHAT it said — the one thing that lets them judge whether
it was worth being interrupted for, and the exact blind spot the heartbeat
history closed.

The text already exists at write time and was simply dropped. Nullable and
staying so: every row written before this migration legitimately has none, and
the card renders without its paragraph rather than inventing one. No backfill
is possible — a hash does not invert.

Revision ID: a1b2c3d4e5f6
Revises: f9a0b1c2d3e4
Create Date: 2026-08-03 15:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interest_notifications",
        sa.Column(
            "content",
            sa.Text(),
            nullable=True,
            comment="Message sent to the user; NULL for rows predating the column.",
        ),
    )


def downgrade() -> None:
    op.drop_column("interest_notifications", "content")
