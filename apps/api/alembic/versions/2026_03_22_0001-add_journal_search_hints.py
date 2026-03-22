"""Add search_hints column to journal_entries.

LLM-generated keywords bridging user vocabulary to entry content
for improved semantic search relevance.

Revision ID: journal_search_hints_001
Revises: usage_limits_001
Create Date: 2026-03-22
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "journal_search_hints_001"
down_revision = "usage_limits_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "journal_entries",
        sa.Column(
            "search_hints",
            postgresql.ARRAY(sa.String(100)),
            nullable=True,
            comment="LLM-generated search keywords bridging user vocabulary to entry content",
        ),
    )


def downgrade() -> None:
    op.drop_column("journal_entries", "search_hints")
