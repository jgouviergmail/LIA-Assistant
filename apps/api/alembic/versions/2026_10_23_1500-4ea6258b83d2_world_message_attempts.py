"""Minimal durable fences for ephemeral direct world text.

Revision ID: 4ea6258b83d2
Revises: c36cda5a9b71
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4ea6258b83d2"
down_revision: str | None = "c36cda5a9b71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "world_message_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("namespace", sa.String(40), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("token", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("content_ready", sa.Boolean(), nullable=False),
        sa.Column("queued_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("running_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('reserved','queued','running','delivered','succeeded','failed','uncertain')",
            name="ck_world_message_attempt_status",
        ),
    )
    op.create_index(
        "ix_world_message_attempt_queue",
        "world_message_attempts",
        ["namespace", "status", "created_at", "id"],
    )
    op.create_index("ix_world_message_attempt_expiry", "world_message_attempts", ["expires_at"])
    op.create_index("ix_world_message_attempts_user_id", "world_message_attempts", ["user_id"])
    op.create_index(
        "ix_world_message_attempts_recipient_id", "world_message_attempts", ["recipient_id"]
    )


def downgrade() -> None:
    op.drop_table("world_message_attempts")
