"""SMS mention bookkeeping and private proactive audit boundaries.
Revision ID: 3fd106ace921
Revises: 1c294a7e820f
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "3fd106ace921"
down_revision: str | None = "1c294a7e820f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sms_messages",
        sa.Column("proactive_mentioned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_sms_unmentioned",
        "sms_messages",
        ["user_id", "received_at", "id"],
        postgresql_where=sa.text("proactive_mentioned_at IS NULL"),
    )
    op.add_column(
        "heartbeat_notifications",
        sa.Column("sensitive_context", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("heartbeat_notifications", "sensitive_context")
    op.drop_index("ix_sms_unmentioned", table_name="sms_messages")
    op.drop_column("sms_messages", "proactive_mentioned_at")
