"""Add injection tracking columns to journal_entries.

Tracks how often each journal entry is injected into prompts
(injection_count) and when it was last used (last_injected_at).
Enables the consolidation service to prioritize frequently-used
entries and identify unused ones for cleanup.

Revision ID: journal_injection_tracking_001
Revises: journal_pgvector_001
Create Date: 2026-03-22
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "journal_injection_tracking_001"
down_revision = "journal_pgvector_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "journal_entries",
        sa.Column(
            "injection_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of times this entry was injected into prompts",
        ),
    )
    op.add_column(
        "journal_entries",
        sa.Column(
            "last_injected_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last time this entry was injected into a prompt (UTC)",
        ),
    )


def downgrade() -> None:
    op.drop_column("journal_entries", "last_injected_at")
    op.drop_column("journal_entries", "injection_count")
