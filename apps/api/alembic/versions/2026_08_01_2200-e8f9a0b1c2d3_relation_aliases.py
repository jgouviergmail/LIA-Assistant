"""relation aliases (manual merge of two relationships)

``fold_name`` decides who is LITERALLY the same person; it cannot know that a
raw phone number and a name are one relationship. Only the user knows, so the
merge is manual and this table records it.

Kept FLAT on purpose: ``alias_key`` always points at the final canonical key,
never at another alias, so a read is one lookup with no chain to walk. Merging
B into C rewrites the rows that pointed at B (path compression at write time).

Reversible: one row per merge, undone by deleting it. The sources are never
rewritten — the CRM is a view over them.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-08-01 22:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the alias table (empty: no merge is ever inferred)."""
    op.create_table(
        "relation_aliases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Owner of the merge.",
        ),
        sa.Column(
            "alias_key",
            sa.String(length=255),
            nullable=False,
            comment="Folded identity that was merged AWAY (fold_name).",
        ),
        sa.Column(
            "canonical_key",
            sa.String(length=255),
            nullable=False,
            comment="Folded identity it now belongs to (fold_name). Never an alias itself.",
        ),
        sa.Column(
            "alias_display_name",
            sa.String(length=255),
            nullable=False,
            comment="Spelling the merged-away side was shown as, so the undo can name it.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "alias_key", name="uq_relation_aliases_user_alias"),
    )
    op.create_index(
        op.f("ix_relation_aliases_user_id"), "relation_aliases", ["user_id"], unique=False
    )
    # The overview resolves every bucket through this table on each request:
    # the lookup is by (user, canonical) when listing what a merge absorbed.
    op.create_index(
        "ix_relation_aliases_user_canonical",
        "relation_aliases",
        ["user_id", "canonical_key"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the table — every merged relationship splits back in two.

    Nothing is lost: the sources always kept their own spellings, so the split
    halves reappear exactly as they were before the merge.
    """
    op.drop_index("ix_relation_aliases_user_canonical", table_name="relation_aliases")
    op.drop_index(op.f("ix_relation_aliases_user_id"), table_name="relation_aliases")
    op.drop_table("relation_aliases")
