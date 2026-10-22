"""Persist SMS sender identities independently of dashboard reads.

Revision ID: 2c7e893a6d10
Revises: 1b8d4f925a10
"""

from alembic import op
import sqlalchemy as sa

revision = "2c7e893a6d10"
down_revision = "1b8d4f925a10"
branch_labels = None
depends_on = None


def _columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("generation", sa.UUID(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("sms_identity_states", *_columns(), sa.UniqueConstraint("user_id"))
    op.create_table(
        "sms_sender_identities",
        *_columns(),
        sa.Column("sender_hash", sa.String(64), nullable=False),
        sa.Column("authority", sa.String(64), nullable=False),
        sa.Column("identity_encrypted", sa.Text(), nullable=False),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "sender_hash"),
    )


def downgrade() -> None:
    op.drop_table("sms_sender_identities")
    op.drop_table("sms_identity_states")
