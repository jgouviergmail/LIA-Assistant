"""The return of an act comes back to the discussion it was begun in.

Revision ID: a28ee9d98f8e
Revises: 7c2e5b9d4a18

A call placed from an annex returned to Main (production 2026-11-14): every
notification resolved « the current Main ». Three acts a person begins in a
discussion now keep where they began — ``phone_calls``, ``meetings`` and
``peer_messages`` gain ``origin_conversation_id`` (``SET NULL`` when the
discussion is purged) and ``origin_conversation_revision`` — and their return
publishes there while that generation lives, else in Main (ADR-378 amendment).
Nullable, no backfill: a row begun before reads as begun nowhere, the return
going to Main as it did. No ``CHECK`` binds the pair: the foreign-key action
nulls the id alone (ADR-276).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a28ee9d98f8e"
down_revision: str | Sequence[str] | None = "7c2e5b9d4a18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("phone_calls", "meetings", "peer_messages")
_ID_COMMENT = (
    "The discussion the act was begun in; its return comes back there while the "
    "generation lives (ADR-378). NULL: begun outside any discussion, or before 2026-11-14."
)
_REVISION_COMMENT = "The generation of that discussion when the act was begun."


def upgrade() -> None:
    """Keep where each act began."""
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "origin_conversation_id",
                sa.Uuid(),
                sa.ForeignKey("conversations.id", ondelete="SET NULL"),
                nullable=True,
                comment=_ID_COMMENT,
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "origin_conversation_revision",
                sa.BigInteger(),
                nullable=True,
                comment=_REVISION_COMMENT,
            ),
        )


def downgrade() -> None:
    """Forget where the acts began; their returns go to Main again."""
    for table in reversed(_TABLES):
        op.drop_column(table, "origin_conversation_revision")
        op.drop_column(table, "origin_conversation_id")
