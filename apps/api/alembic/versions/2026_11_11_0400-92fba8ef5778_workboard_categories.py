"""Workboard categories (ADR-276): the lanes of a board.

A category is a name the OWNER of a board files tickets under; the board draws
one lane per category, and a ticket filed under nothing sits in the unfiled
lane. Two shapes carry a decision:

- ``workboard_tickets.category_id`` is **nullable and SET NULL**: deleting a
  category sends its tickets back to the unfiled lane, it never deletes
  somebody's work. One column, the OWNER's category — a peer who holds the
  ticket reads the lane and cannot refile it (owner arbitration, 2026-11-11).
- uniqueness is held on ``name_key``, the name FOLDED in Python by the one
  folding authority (``fold_name``, ADR-185). A functional index re-expressing
  the fold in SQL would make the database a second authority on what « the
  same name » means, and the two diverge on ligatures and on ``ß``.

The unique constraint leads with the owner, so it also serves every « my
categories » read: no separate index on the owner.

Additive and empty: no existing row is rewritten, every ticket starts unfiled.

Revision ID: 92fba8ef5778
Revises: d8f6b4a10c2e
Create Date: 2026-11-11 04:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "92fba8ef5778"
down_revision: str | None = "d8f6b4a10c2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATEGORY_COMMENT = (
    "The OWNER's category — the board lane it is filed under. NULL means "
    "not filed; SET NULL when the category goes, never the ticket."
)


def upgrade() -> None:
    """Create the categories table and the ticket's nullable category."""
    op.create_table(
        "workboard_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Whose category. Dies with the account.",
        ),
        sa.Column(
            "name",
            sa.Text(),
            nullable=False,
            comment="What the person called it, trimmed, single-spaced.",
        ),
        sa.Column(
            "name_key",
            sa.Text(),
            nullable=False,
            comment="fold_name(name): the identity uniqueness is held on.",
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            comment="Order of the lane on the owner's board, dense from 0.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "name_key", name="uq_workboard_categories_owner_name"),
    )
    op.add_column(
        "workboard_tickets",
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment=_CATEGORY_COMMENT,
        ),
    )
    op.create_foreign_key(
        "fk_workboard_tickets_category_id",
        "workboard_tickets",
        "workboard_categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_workboard_tickets_category_id", "workboard_tickets", ["category_id"], unique=False
    )


def downgrade() -> None:
    """Drop the lanes; every ticket stays, filed under nothing."""
    op.drop_index("ix_workboard_tickets_category_id", table_name="workboard_tickets")
    op.drop_constraint("fk_workboard_tickets_category_id", "workboard_tickets", type_="foreignkey")
    op.drop_column("workboard_tickets", "category_id")
    op.drop_table("workboard_categories")
