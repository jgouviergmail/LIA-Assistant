"""add relation_favorites

Personal-CRM favorites: a starred relationship must survive its live signals
(open loops, calls) expiring, so the star persists the folded identity key and
the spelling the user starred. One row per (user, name_key).

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-07-30 06:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the relation_favorites table."""
    op.create_table(
        "relation_favorites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Owner of the star.",
        ),
        sa.Column(
            "name_key",
            sa.String(length=255),
            nullable=False,
            comment="Accent/case-folded relationship identity (fold_name).",
        ),
        sa.Column(
            "display_name",
            sa.String(length=255),
            nullable=False,
            comment="Spelling the user starred (fallback rendering).",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name_key", name="uq_relation_favorites_user_name"),
    )
    op.create_index("ix_relation_favorites_user_id", "relation_favorites", ["user_id"])


def downgrade() -> None:
    """Drop the relation_favorites table."""
    op.drop_index("ix_relation_favorites_user_id", table_name="relation_favorites")
    op.drop_table("relation_favorites")
