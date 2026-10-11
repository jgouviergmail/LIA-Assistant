"""Version journal evidence and derived portraits; coordinate consolidation.

Revision ID: a92d4e713b60
Revises: f19c83e2a6b0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a92d4e713b60"
down_revision: str | None = "f19c83e2a6b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "journal_entries",
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
    )
    for column in (
        sa.Column("journal_revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("journal_consolidated_revision", sa.BigInteger(), nullable=True),
        sa.Column("journal_last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("journal_last_attempt_status", sa.String(24), nullable=True),
        sa.Column("journal_consolidation_owner", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("journal_consolidation_held_until", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("users", column)
    op.create_table(
        "journal_evidence_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "journal_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_revision", sa.BigInteger(), nullable=False),
        sa.Column("event_key", sa.String(200), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column(
            "source_conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('evidence', 'contradiction')", name="ck_journal_evidence_outcome"
        ),
        sa.CheckConstraint("rule_revision > 0", name="ck_journal_evidence_revision"),
    )
    op.create_index(
        "uq_journal_evidence_rule_event",
        "journal_evidence_events",
        ["journal_entry_id", "rule_revision", "event_key"],
        unique=True,
    )
    op.create_index("ix_journal_evidence_user", "journal_evidence_events", ["user_id"])
    # Old counters have no independent event identities. Retain their totals,
    # but require independently captured events before high confidence.
    op.execute("UPDATE journal_entries SET confidence = 'medium' WHERE confidence = 'high'")
    # An unversioned portrait cannot be proved current; rebuild lazily.
    op.execute(
        "UPDATE users SET journal_portrait_full = NULL, journal_portrait_brief = NULL, journal_portrait_compiled_at = NULL, journal_portrait_sources = NULL"
    )


def downgrade() -> None:
    op.drop_table("journal_evidence_events")
    for column in (
        "journal_consolidation_held_until",
        "journal_consolidation_owner",
        "journal_last_attempt_status",
        "journal_last_attempted_at",
        "journal_consolidated_revision",
        "journal_revision",
    ):
        op.drop_column("users", column)
    op.drop_column("journal_entries", "revision")
