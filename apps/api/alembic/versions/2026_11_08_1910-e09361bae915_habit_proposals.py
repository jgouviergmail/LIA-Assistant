"""What LIA offers from what it learned, and the person's decision (ADR-375).

Revision ID: e09361bae915
Revises: 962ddad22cf1
Create Date: 2026-11-08 19:10:00.000000

One row per (person, kind, key). The two vocabularies are frozen HERE, as CHECK
constraints, so replaying this revision never depends on a later list in the
code: a new kind or status is a new migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e09361bae915"
down_revision: str | Sequence[str] | None = "962ddad22cf1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Mirrored EXACTLY by the model's ``comment=`` (the replay check compares them).
_PAYLOAD = "Facts the card shows and the action reads (no sentence, no message text)."
_RESURFACE = "When a dismissed or accepted proposal may reopen; NULL never."
_CHAT_SHOWN = "When the chat last showed it under an answer."

_STATUSES = "('open', 'accepted', 'dismissed', 'refused')"
_KINDS = (
    "('automate_need', 'shift_routine', 'fix_routine', "
    "'extend_notification_window', 'review_notifications', 'connect_source')"
)


def upgrade() -> None:
    """Create the proposals table, its identity, its read index and its vocabularies."""
    op.create_table(
        "habit_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment=_PAYLOAD
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("resurface_after", sa.DateTime(timezone=True), nullable=True, comment=_RESURFACE),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chat_shown_at", sa.DateTime(timezone=True), nullable=True, comment=_CHAT_SHOWN),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "key", name="uq_habit_proposals_user_kind_key"),
        sa.CheckConstraint(f"status IN {_STATUSES}", name="ck_habit_proposals_status"),
        sa.CheckConstraint(f"kind IN {_KINDS}", name="ck_habit_proposals_kind"),
    )
    op.create_index(
        "ix_habit_proposals_user_status", "habit_proposals", ["user_id", "status"], unique=False
    )


def downgrade() -> None:
    """Drop the proposals table (the decisions go with it)."""
    op.drop_index("ix_habit_proposals_user_status", table_name="habit_proposals")
    op.drop_table("habit_proposals")
