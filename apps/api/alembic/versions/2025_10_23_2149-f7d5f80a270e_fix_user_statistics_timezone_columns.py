"""fix_user_statistics_timezone_columns

Revision ID: f7d5f80a270e
Revises: 62f067eda14d
Create Date: 2025-10-23 21:49:38.636203

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7d5f80a270e'
down_revision: str | None = '62f067eda14d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Convert datetime columns to timezone-aware (TIMESTAMP WITH TIME ZONE)
    # This fixes the "can't subtract offset-naive and offset-aware datetimes" error

    op.execute("""
        ALTER TABLE user_statistics
        ALTER COLUMN current_cycle_start TYPE TIMESTAMP WITH TIME ZONE
        USING current_cycle_start AT TIME ZONE 'UTC'
    """)

    op.execute("""
        ALTER TABLE user_statistics
        ALTER COLUMN last_updated_at TYPE TIMESTAMP WITH TIME ZONE
        USING last_updated_at AT TIME ZONE 'UTC'
    """)


def downgrade() -> None:
    # Revert to timezone-naive columns
    op.execute("""
        ALTER TABLE user_statistics
        ALTER COLUMN current_cycle_start TYPE TIMESTAMP WITHOUT TIME ZONE
    """)

    op.execute("""
        ALTER TABLE user_statistics
        ALTER COLUMN last_updated_at TYPE TIMESTAMP WITHOUT TIME ZONE
    """)

