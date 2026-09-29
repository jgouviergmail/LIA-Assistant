"""Native decision catalogue types and durable meeting selection spend.

Revision ID: 8bd197e03fa6
Revises: c6b33e35a16e

Enum additions commit before the following migration uses their values. Downgrade
keeps enum labels (PostgreSQL cannot drop a used enum label safely).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8bd197e03fa6"
down_revision: str | None = "c6b33e35a16e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE llm_provider_enum ADD VALUE IF NOT EXISTS 'typesafe'")
        op.execute("ALTER TYPE llm_model_kind_enum ADD VALUE IF NOT EXISTS 'decision'")
    op.add_column(
        "meetings",
        sa.Column(
            "template_selection_usage",
            postgresql.JSONB(none_as_null=True),
            nullable=True,
            comment="Native selection charges by run, including unsuccessful processing attempts",
        ),
    )


def downgrade() -> None:
    spent = op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM meetings WHERE template_selection_usage IS NOT NULL)")
    )
    if spent:
        raise RuntimeError(
            "Native meeting accounting exists; use the Jev OFF switch instead of dropping its history."
        )
    op.drop_column("meetings", "template_selection_usage")
