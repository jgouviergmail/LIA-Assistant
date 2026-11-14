"""Record proven file usages separately from generation provenance.

Revision ID: a92b4c6d8e05
Revises: f81a3b5c7d94
"""

from collections.abc import Sequence

import sqlalchemy as sa
import structlog
from alembic import op

revision: str = "a92b4c6d8e05"
down_revision: str | Sequence[str] | None = "f81a3b5c7d94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "conversation_attachment_usages"


def upgrade() -> None:
    """Backfill only owner-matched UUIDs the archived attachment block actually names."""
    op.add_column("attachments", sa.Column("deletion_reason", sa.String(30), nullable=True))
    op.create_check_constraint(
        "ck_attachments_deletion_reason",
        "attachments",
        "status <> 'deleting' OR deletion_reason IS NOT NULL",
    )
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "attachment_id",
            sa.Uuid(),
            sa.ForeignKey("attachments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("conversation_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "attachment_id", "conversation_id", name="uq_conversation_attachment_usage"
        ),
        sa.CheckConstraint(
            "conversation_revision >= 0", name="ck_conversation_attachment_usage_revision"
        ),
    )
    op.create_index(
        "ix_conversation_attachment_usages_source",
        _TABLE,
        ["conversation_id", "conversation_revision"],
    )
    # archive_first.turn_attachment_meta writes this exact block, not the
    # generated card's URL and not Attachment.conversation_id (provenance).
    op.execute(sa.text("""
            INSERT INTO conversation_attachment_usages
                (id, attachment_id, conversation_id, conversation_revision, created_at, updated_at)
            SELECT gen_random_uuid(), proven.attachment_id, proven.conversation_id,
                   proven.revision, now(), now()
            FROM (
                SELECT DISTINCT a.id AS attachment_id, c.id AS conversation_id, c.revision
                FROM conversation_messages m
                JOIN conversations c ON c.id = m.conversation_id
                CROSS JOIN LATERAL jsonb_array_elements(
                    CASE WHEN jsonb_typeof(m.message_metadata -> 'attachments') = 'array'
                         THEN m.message_metadata -> 'attachments' ELSE '[]'::jsonb END
                ) AS entry
                JOIN attachments a ON a.id = CASE
                    WHEN entry ->> 'id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                    THEN (entry ->> 'id')::uuid END
                WHERE a.user_id = c.user_id AND c.deleted_at IS NULL
            ) proven
            ON CONFLICT ON CONSTRAINT uq_conversation_attachment_usage DO NOTHING
            """))
    unattributed = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM attachments a WHERE a.origin = 'upload' AND NOT EXISTS "
            "(SELECT 1 FROM conversation_attachment_usages u WHERE u.attachment_id = a.id)"
        )
    )
    structlog.get_logger(__name__).info(
        "attachment_usage_backfill_completed", unattributed_uploads=unattributed
    )


def downgrade() -> None:
    """Keep unfinished cleanup evidence; otherwise remove only the derived relation."""
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM attachments WHERE status='deleting')")
    ):
        raise RuntimeError("Cannot remove attachment cleanup evidence while deletion is pending")
    op.drop_table(_TABLE)
    op.drop_constraint("ck_attachments_deletion_reason", "attachments", type_="check")
    op.drop_column("attachments", "deletion_reason")
