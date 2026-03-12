"""Add LLM pricing tables

Revision ID: llm_pricing_001
Revises: cd42ca544c43
Create Date: 2025-10-20 18:08:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'llm_pricing_001'
down_revision: str | None = 'cd42ca544c43'  # Previous migration
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create llm_model_pricing table
    op.create_table(
        'llm_model_pricing',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False, comment="LLM model identifier (e.g., 'gpt-5', 'o1-mini')"),
        sa.Column('input_price_per_1m_tokens', sa.DECIMAL(10, 6), nullable=False, comment="Price in USD per 1 million input tokens"),
        sa.Column('cached_input_price_per_1m_tokens', sa.DECIMAL(10, 6), nullable=True, comment="Price in USD per 1M cached input tokens (NULL if not supported)"),
        sa.Column('output_price_per_1m_tokens', sa.DECIMAL(10, 6), nullable=False, comment="Price in USD per 1 million output tokens"),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False, comment="Date from which this pricing is effective"),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true', comment="Whether this pricing entry is currently active"),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('model_name', 'effective_from', name='uq_model_effective_from')
    )

    # Create indexes for llm_model_pricing
    op.create_index('ix_llm_model_pricing_model_name', 'llm_model_pricing', ['model_name'])
    op.create_index('ix_llm_model_pricing_is_active', 'llm_model_pricing', ['is_active'])
    op.create_index('ix_llm_model_pricing_active_lookup', 'llm_model_pricing', ['model_name', 'is_active'])

    # Create currency_exchange_rates table
    op.create_table(
        'currency_exchange_rates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('from_currency', sa.String(length=3), nullable=False, comment="Source currency code (ISO 4217, e.g., 'USD')"),
        sa.Column('to_currency', sa.String(length=3), nullable=False, comment="Target currency code (ISO 4217, e.g., 'EUR')"),
        sa.Column('rate', sa.DECIMAL(10, 6), nullable=False, comment="Exchange rate (1 from_currency = rate to_currency)"),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False, comment="Date from which this rate is effective"),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true', comment="Whether this rate entry is currently active"),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('from_currency', 'to_currency', 'effective_from', name='uq_currency_pair_effective_from')
    )

    # Create indexes for currency_exchange_rates
    op.create_index('ix_currency_exchange_rates_from_currency', 'currency_exchange_rates', ['from_currency'])
    op.create_index('ix_currency_exchange_rates_to_currency', 'currency_exchange_rates', ['to_currency'])
    op.create_index('ix_currency_exchange_rates_is_active', 'currency_exchange_rates', ['is_active'])
    op.create_index('ix_currency_exchange_rates_active_lookup', 'currency_exchange_rates', ['from_currency', 'to_currency', 'is_active'])


def downgrade() -> None:
    # Drop currency_exchange_rates table
    op.drop_index('ix_currency_exchange_rates_active_lookup', table_name='currency_exchange_rates')
    op.drop_index('ix_currency_exchange_rates_is_active', table_name='currency_exchange_rates')
    op.drop_index('ix_currency_exchange_rates_to_currency', table_name='currency_exchange_rates')
    op.drop_index('ix_currency_exchange_rates_from_currency', table_name='currency_exchange_rates')
    op.drop_table('currency_exchange_rates')

    # Drop llm_model_pricing table
    op.drop_index('ix_llm_model_pricing_active_lookup', table_name='llm_model_pricing')
    op.drop_index('ix_llm_model_pricing_is_active', table_name='llm_model_pricing')
    op.drop_index('ix_llm_model_pricing_model_name', table_name='llm_model_pricing')
    op.drop_table('llm_model_pricing')
