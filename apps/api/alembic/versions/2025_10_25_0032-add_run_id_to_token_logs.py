"""add_run_id_to_token_usage_logs

Revision ID: token_run_id_001
Revises: conversation_persist_001
Create Date: 2025-10-25 00:32:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'token_run_id_001'
down_revision: str | None = 'conversation_persist_001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add run_id column to token_usage_logs
    op.add_column('token_usage_logs', sa.Column('run_id', sa.String(length=255), nullable=False))

    # Create index on run_id for JOIN performance
    op.create_index(op.f('ix_token_usage_logs_run_id'), 'token_usage_logs', ['run_id'], unique=False)


def downgrade() -> None:
    # Remove index and column
    op.drop_index(op.f('ix_token_usage_logs_run_id'), table_name='token_usage_logs')
    op.drop_column('token_usage_logs', 'run_id')
