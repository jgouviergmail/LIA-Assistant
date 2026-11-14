"""Separate discussion identity from runtime and retain creation receipts.

Revision ID: b43c6d9e1a72
Revises: ea21f834b670

Drain old application writers before this migration: an old writer cannot
provide runtime_id. Historical business and checkpoint UUIDs remain unchanged.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b43c6d9e1a72"
down_revision: str | Sequence[str] | None = "ea21f834b670"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen migration data: the Unicode strip set used by the deployed validator.
_TITLE_WHITESPACE = (
    "\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)


def upgrade() -> None:
    """Preserve every legacy UUID and replace only singleton cardinality."""
    op.add_column(
        "conversations", sa.Column("kind", sa.String(9), nullable=False, server_default="main")
    )
    op.add_column(
        "conversations", sa.Column("revision", sa.BigInteger(), nullable=False, server_default="0")
    )
    op.add_column(
        "conversations", sa.Column("runtime_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.execute(sa.text("UPDATE conversations SET runtime_id = id"))
    op.alter_column("conversations", "runtime_id", nullable=False)
    op.create_unique_constraint("uq_conversations_runtime_id", "conversations", ["runtime_id"])
    op.create_check_constraint(
        "conversation_kind", "conversations", "kind IN ('main', 'secondary')"
    )
    op.create_check_constraint("ck_conversations_revision", "conversations", "revision >= 0")
    op.create_check_constraint(
        "ck_conversations_secondary_title",
        "conversations",
        sa.or_(
            sa.column("kind") != "secondary",
            sa.and_(
                sa.column("title").is_not(None),
                sa.func.length(sa.func.btrim(sa.column("title"), _TITLE_WHITESPACE)) > 0,
            ),
        ),
    )
    op.drop_constraint("uq_conversations_user_id", "conversations", type_="unique")
    op.create_index(
        "uq_conversations_primary_user",
        "conversations",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'main'"),
    )
    op.create_table(
        "conversation_creation_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "request_id", name="uq_conversation_creation_attempt"),
    )


def downgrade() -> None:
    """Refuse any rollback that would lose identity, cardinality or retry history."""
    unsafe = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM conversations "
            "WHERE kind <> 'main' OR revision <> 0 OR runtime_id <> id) "
            "OR EXISTS (SELECT 1 FROM conversation_creation_receipts)"
        )
    )
    if unsafe:
        raise RuntimeError(
            "Cannot restore singleton schema after secondary creation or runtime rotation; keep compatible code and disable creation."
        )
    op.drop_table("conversation_creation_receipts")
    op.drop_index("uq_conversations_primary_user", table_name="conversations")
    op.create_unique_constraint("uq_conversations_user_id", "conversations", ["user_id"])
    for name in (
        "ck_conversations_secondary_title",
        "ck_conversations_revision",
        "conversation_kind",
    ):
        op.drop_constraint(name, "conversations", type_="check")
    op.drop_constraint("uq_conversations_runtime_id", "conversations", type_="unique")
    for name in ("runtime_id", "revision", "kind"):
        op.drop_column("conversations", name)
