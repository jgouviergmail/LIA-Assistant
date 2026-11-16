"""Index where each act began, so a purged discussion finds its acts at once.

Revision ID: 7fb09b785088
Revises: a28ee9d98f8e

``phone_calls``, ``meetings`` and ``peer_messages`` keep the discussion an act
was begun in (``origin_conversation_id``, ``SET NULL`` when the discussion is
purged). A foreign key without an index makes every purge of a discussion scan
the three tables to null the references: the account purge deletes each of its
discussions, one scan per table each. The plain index the model declares
(``index=True``) serves that lookup.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7fb09b785088"
down_revision: str | Sequence[str] | None = "a28ee9d98f8e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("phone_calls", "meetings", "peer_messages")
_COLUMN = "origin_conversation_id"


def upgrade() -> None:
    """Index the origin discussion of every act table."""
    for table in _TABLES:
        op.create_index(op.f(f"ix_{table}_{_COLUMN}"), table, [_COLUMN])


def downgrade() -> None:
    """Drop the origin indexes; the references stay."""
    for table in reversed(_TABLES):
        op.drop_index(op.f(f"ix_{table}_{_COLUMN}"), table_name=table)
