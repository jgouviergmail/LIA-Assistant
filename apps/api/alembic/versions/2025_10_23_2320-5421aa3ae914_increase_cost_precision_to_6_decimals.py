"""increase_cost_precision_to_6_decimals

Revision ID: 5421aa3ae914
Revises: f7d5f80a270e
Create Date: 2025-10-23 23:20:00.160473

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5421aa3ae914'
down_revision: str | None = 'f7d5f80a270e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Increase cost_eur precision from NUMERIC(12,2) to NUMERIC(12,6).

    Required for storing micro-costs from LLM API calls (e.g., 0.000757 EUR).
    Previously, costs < 0.01 EUR rounded to 0.00 EUR.
    """
    # Alter user_statistics cost columns
    op.alter_column(
        'user_statistics',
        'total_cost_eur',
        type_=sa.Numeric(precision=12, scale=6),
        existing_type=sa.Numeric(precision=12, scale=2),
        existing_nullable=False,
    )
    op.alter_column(
        'user_statistics',
        'cycle_cost_eur',
        type_=sa.Numeric(precision=12, scale=6),
        existing_type=sa.Numeric(precision=12, scale=2),
        existing_nullable=False,
    )


def downgrade() -> None:
    """
    Revert cost_eur precision from NUMERIC(12,6) back to NUMERIC(12,2).

    WARNING: This will truncate values and lose precision!
    """
    # Revert user_statistics cost columns
    op.alter_column(
        'user_statistics',
        'total_cost_eur',
        type_=sa.Numeric(precision=12, scale=2),
        existing_type=sa.Numeric(precision=12, scale=6),
        existing_nullable=False,
    )
    op.alter_column(
        'user_statistics',
        'cycle_cost_eur',
        type_=sa.Numeric(precision=12, scale=2),
        existing_type=sa.Numeric(precision=12, scale=6),
        existing_nullable=False,
    )
