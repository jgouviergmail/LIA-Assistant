"""Fence cached voice choices against a library deletion (ADR-345).

Revision ID: 7f428c3e0a19
Revises: 4c2e8a6f1d3b
Create Date: 2026-10-15 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7f428c3e0a19"
down_revision: str | None = "4c2e8a6f1d3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No seed is needed: absence denotes the catalogue before its first deletion."""
    op.create_table(
        "fishaudio_catalogue_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "pending_removals",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "id = '00000000-0000-0000-0000-000000000000'::uuid",
            name="ck_fishaudio_catalogue_singleton",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(pending_removals) = 'object'", name="ck_fishaudio_pending_removals_object"
        ),
    )


def downgrade() -> None:
    """Drop revision state without changing the voices or preferences themselves."""
    op.drop_table("fishaudio_catalogue_revisions")
