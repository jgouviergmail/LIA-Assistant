"""provenance: bounded references from a belief to the signal behind it

A journal entry says "prefers written summaries over calls"; a memory says
"allergic to shellfish". Both are conclusions LIA drew, both are injected into
prompts, and neither could answer the one question that makes them correctable:
why do you think that?

The material existed and was thrown away. Journal entries carried
``evidence_count`` and ``contradiction_count`` — bare counters — while the
deferred self-evaluation knew, at the instant it incremented one, exactly which
turn produced the signal. Memories carried nothing at all.

What this table stores is a POINTER and a timestamp, never the words. A copy
would be a second, permanent home for content the user can delete elsewhere,
and their deletion would stop being a deletion. Hence:

- ``conversation_id`` and ``message_id`` are real foreign keys with ON DELETE
  SET NULL. Deleting a conversation nulls the pointer and LEAVES the row,
  dated: that row is the tombstone. It says something supported this belief and
  that the something is gone — it never brings the content back;
- ``journal_entry_id`` / ``memory_id`` / ``interest_id`` CASCADE instead: a
  reference to a deleted belief has no subject, so there is nothing left to
  explain. An INTEREST is a belief too — "you seem to care about X" — so it
  lives in the same table rather than growing a column of its own elsewhere.

The CHECK constraint enforces exactly one subject per row. A polymorphic
(kind, id) pair cannot be a foreign key, and without a foreign key the
tombstone above would be guaranteed by nothing at all.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-04 09:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the provenance reference table."""
    op.create_table(
        "provenance_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("interest_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["interest_id"], ["user_interests.id"], ondelete="CASCADE"),
        # SET NULL, never CASCADE — this is what leaves a tombstone behind.
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["conversation_messages.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "(journal_entry_id IS NOT NULL)::int + (memory_id IS NOT NULL)::int"
            " + (interest_id IS NOT NULL)::int = 1",
            name="ck_provenance_exactly_one_subject",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_provenance_journal_entry",
        "provenance_references",
        ["journal_entry_id", "captured_at"],
    )
    op.create_index("ix_provenance_memory", "provenance_references", ["memory_id", "captured_at"])
    op.create_index(
        "ix_provenance_interest", "provenance_references", ["interest_id", "captured_at"]
    )
    op.create_index("ix_provenance_user", "provenance_references", ["user_id"])


def downgrade() -> None:
    """Drop the provenance reference table.

    Nothing to preserve: the table holds only pointers, and every one of them
    still exists on the row it points at.
    """
    op.drop_index("ix_provenance_user", table_name="provenance_references")
    op.drop_index("ix_provenance_interest", table_name="provenance_references")
    op.drop_index("ix_provenance_memory", table_name="provenance_references")
    op.drop_index("ix_provenance_journal_entry", table_name="provenance_references")
    op.drop_table("provenance_references")
