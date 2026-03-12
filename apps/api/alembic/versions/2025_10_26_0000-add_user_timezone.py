"""add_user_timezone

Revision ID: user_timezone_001
Revises: token_run_id_001
Create Date: 2025-10-26 00:00:00.000000

Adds timezone field to users table for personalized timestamp display.
Default: Europe/Paris (can be updated via user preferences in future).
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'user_timezone_001'
down_revision: str | None = 'token_run_id_001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add timezone column to users table.

    - Column: timezone (String 50)
    - Default: 'Europe/Paris'
    - Nullable: False (with server_default for existing rows)
    - Use case: Personalized cache age display ("il y a 2 min" in user's timezone)
    """
    op.add_column(
        'users',
        sa.Column(
            'timezone',
            sa.String(length=50),
            nullable=False,
            server_default='Europe/Paris',  # Default for existing users
            comment='User timezone (IANA timezone name, e.g., Europe/Paris, America/New_York)',
        )
    )


def downgrade() -> None:
    """
    Remove timezone column from users table.
    """
    op.drop_column('users', 'timezone')
