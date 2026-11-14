"""Retain lifecycle identity and cleanup debt independently of deleted sources.

Revision ID: d25e7f9a1b38
Revises: c14d6e8f0a27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d25e7f9a1b38"
down_revision = "c14d6e8f0a27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create content-free operational receipts without a destructive CASCADE."""
    op.create_table(
        "conversation_operations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "reset",
                "delete",
                name="conversation_operation_action",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "conversation_kind",
            sa.Enum(
                "main",
                "secondary",
                name="conversation_operation_kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("old_revision", sa.BigInteger(), nullable=False),
        sa.Column("runtime_id", sa.UUID(), nullable=False),
        sa.Column("new_revision", sa.BigInteger(), nullable=True),
        sa.Column("attachment_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("previous_message_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "pending",
                "running",
                "retry_wait",
                "needs_attention",
                "succeeded",
                name="conversation_cleanup_state",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "phase",
            sa.Enum(
                "checkpoint",
                "context",
                "pending",
                "files",
                "complete",
                name="conversation_cleanup_phase",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("owner_token", sa.UUID(), nullable=True),
        sa.Column("fence", sa.BigInteger(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("claim_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.UniqueConstraint("user_id", "request_id", name="uq_conversation_operation_request"),
        sa.CheckConstraint(
            "old_revision >= 0 AND fence >= 0 AND attempts >= 0", name="ck_operation_counts"
        ),
        sa.CheckConstraint(
            "(action = 'reset' AND new_revision IS NOT NULL AND new_revision = old_revision + 1) OR (action = 'delete' AND new_revision IS NULL)",
            name="ck_operation_revision",
        ),
        sa.CheckConstraint(
            "(state = 'succeeded') = (completed_at IS NOT NULL) AND (state = 'succeeded') = (phase = 'complete')",
            name="ck_operation_complete",
        ),
        sa.CheckConstraint(
            "(state = 'running' AND owner_token IS NOT NULL AND claim_until IS NOT NULL) OR (state <> 'running' AND owner_token IS NULL AND claim_until IS NULL)",
            name="ck_operation_claim",
        ),
    )
    op.create_index(
        "ix_conversation_operations_pending",
        "conversation_operations",
        ["state", "next_attempt_at", "id"],
    )


def downgrade() -> None:
    """Never discard outstanding debt or a retained retry identity."""
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM conversation_operations)")):
        raise RuntimeError("Cannot discard retained conversation operations")
    op.drop_table("conversation_operations")
