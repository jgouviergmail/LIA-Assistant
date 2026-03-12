"""add_token_and_message_tracking_tables

Revision ID: 62f067eda14d
Revises: llm_pricing_001
Create Date: 2025-10-23 23:08:19.903126

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '62f067eda14d'
down_revision: str | None = 'llm_pricing_001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create token_usage_logs table (audit trail per LLM node call)
    op.create_table(
        'token_usage_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('node_name', sa.String(length=100), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cached_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=False, server_default='0.0'),
        sa.Column('cost_eur', sa.Numeric(precision=10, scale=6), nullable=False, server_default='0.0'),
        sa.Column('usd_to_eur_rate', sa.Numeric(precision=10, scale=6), nullable=False, server_default='1.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )

    # Indexes for token_usage_logs
    op.create_index('ix_token_usage_logs_user_id', 'token_usage_logs', ['user_id'])
    op.create_index('ix_token_usage_logs_user_created', 'token_usage_logs', ['user_id', 'created_at'])
    op.create_index('ix_token_usage_logs_node_name', 'token_usage_logs', ['node_name'])

    # Create message_token_summary table (aggregated per message)
    op.create_table(
        'message_token_summary',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('session_id', sa.String(length=255), nullable=False),
        sa.Column('run_id', sa.String(length=255), nullable=False),
        sa.Column('total_prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_cached_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_cost_eur', sa.Numeric(precision=10, scale=6), nullable=False, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id')
    )

    # Indexes for message_token_summary
    op.create_index('ix_message_token_summary_user_id', 'message_token_summary', ['user_id'])
    op.create_index('ix_message_token_summary_session_id', 'message_token_summary', ['session_id'])
    op.create_index('ix_message_token_summary_run_id', 'message_token_summary', ['run_id'])
    op.create_index('ix_message_token_summary_user_created', 'message_token_summary', ['user_id', 'created_at'])

    # Create user_statistics table (pre-calculated cache for dashboard)
    op.create_table(
        'user_statistics',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),

        # Lifetime totals
        sa.Column('total_prompt_tokens', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('total_completion_tokens', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('total_cached_tokens', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('total_cost_eur', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('total_messages', sa.BigInteger(), nullable=False, server_default='0'),

        # Current billing cycle
        sa.Column('current_cycle_start', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('cycle_prompt_tokens', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('cycle_completion_tokens', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('cycle_cached_tokens', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('cycle_cost_eur', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('cycle_messages', sa.BigInteger(), nullable=False, server_default='0'),

        sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )

    # Index for user_statistics
    op.create_index('ix_user_statistics_user_id', 'user_statistics', ['user_id'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('ix_user_statistics_user_id', table_name='user_statistics')
    op.drop_table('user_statistics')

    op.drop_index('ix_message_token_summary_user_created', table_name='message_token_summary')
    op.drop_index('ix_message_token_summary_run_id', table_name='message_token_summary')
    op.drop_index('ix_message_token_summary_session_id', table_name='message_token_summary')
    op.drop_index('ix_message_token_summary_user_id', table_name='message_token_summary')
    op.drop_table('message_token_summary')

    op.drop_index('ix_token_usage_logs_node_name', table_name='token_usage_logs')
    op.drop_index('ix_token_usage_logs_user_created', table_name='token_usage_logs')
    op.drop_index('ix_token_usage_logs_user_id', table_name='token_usage_logs')
    op.drop_table('token_usage_logs')
