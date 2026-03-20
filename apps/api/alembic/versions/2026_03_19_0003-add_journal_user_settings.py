"""Add user-configurable journal settings columns.

Revision ID: journals_002
Revises: journals_001
Create Date: 2026-03-19

Adds two new user-configurable columns to the users table:
- journal_max_entry_chars: Max characters per individual journal entry
- journal_context_max_results: Max entries returned by semantic search
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "journals_002"
down_revision: str | None = "journals_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add journal user settings columns."""
    # Skip if columns already exist (idempotent for dev environments
    # where columns were added manually via SQL)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    if "journal_max_entry_chars" not in existing_columns:
        op.add_column(
            "users",
            sa.Column(
                "journal_max_entry_chars",
                sa.Integer(),
                nullable=False,
                server_default="2000",
                comment="Max characters per individual journal entry.",
            ),
        )

    if "journal_context_max_results" not in existing_columns:
        op.add_column(
            "users",
            sa.Column(
                "journal_context_max_results",
                sa.Integer(),
                nullable=False,
                server_default="10",
                comment="Max entries returned by semantic search for context injection.",
            ),
        )


def downgrade() -> None:
    """Remove journal user settings columns."""
    op.drop_column("users", "journal_context_max_results")
    op.drop_column("users", "journal_max_entry_chars")
