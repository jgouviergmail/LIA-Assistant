"""add_user_language

Revision ID: user_language_001
Revises: add_token_usage_indexes_for_lifetime_metrics
Create Date: 2025-11-07 00:00:00.000000

Adds language field to users table for internationalized emails and notifications.
Default: fr (French) - Supports: fr, en, es, de, it.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'user_language_001'
down_revision: str | None = 'token_usage_indexes_lifetime'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add language column to users table.

    - Column: language (String 10)
    - Default: 'fr' (French)
    - Nullable: False (with server_default for existing rows)
    - Use case: Internationalized emails and notifications in user's preferred language
    - Supported languages: fr, en, es, de, it, zh-CN (ISO 639-1 codes + locale)
    """
    op.add_column(
        'users',
        sa.Column(
            'language',
            sa.String(length=10),
            nullable=False,
            server_default='fr',  # Default for existing users
            comment='User preferred language (ISO 639-1 code: fr, en, es, de, it, zh-CN) for emails and notifications',
        )
    )


def downgrade() -> None:
    """
    Remove language column from users table.
    """
    op.drop_column('users', 'language')
