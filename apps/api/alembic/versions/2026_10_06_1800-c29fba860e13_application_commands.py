"""Durable encrypted application command identity and fenced completion.

Revision ID: c29fba860e13
Revises: a4c7e9f1b3d5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c29fba860e13"
down_revision: str | None = "a4c7e9f1b3d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("draft_id", sa.String(100), nullable=False),
        sa.Column("operation_id", sa.String(100), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("content_encrypted", sa.Text(), nullable=False),
        sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draft_id"),
    )
    op.create_index(
        "ix_application_commands_actor_phase", "application_commands", ["actor_id", "phase"]
    )


def downgrade() -> None:
    op.drop_index("ix_application_commands_actor_phase", table_name="application_commands")
    op.drop_table("application_commands")
