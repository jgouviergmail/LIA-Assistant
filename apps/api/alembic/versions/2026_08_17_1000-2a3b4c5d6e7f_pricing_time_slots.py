"""Add UTC time-slot tariffs to llm_model_pricing (ADR-223).

Some providers bill text models by time of day (DeepSeek: peak windows
01:00-04:00 and 06:00-10:00 UTC, 50% off elsewhere). The nullable JSONB
``time_slots`` column carries the optional windowed tariff on each
temporally-versioned pricing row; NULL keeps the existing flat-pricing
behavior byte-for-byte, so no data backfill is needed (owner decision
2026-08-17: existing databases get their slots through the admin UI).

Revision ID: 2a3b4c5d6e7f
Revises: 1f2a3b4c5d6e
Create Date: 2026-08-17 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "2a3b4c5d6e7f"
down_revision: str | None = "1f2a3b4c5d6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable time_slots column (flat pricing stays the default)."""
    op.add_column(
        "llm_model_pricing",
        sa.Column(
            "time_slots",
            JSONB,
            nullable=True,
            comment=(
                "Optional UTC time-based tariff (ADR-223): list of "
                '{"start_utc":"HH:MM","end_utc":"HH:MM","input_unit_price":float,'
                '"cached_input_unit_price":float|null,"output_unit_price":float}. '
                "[start,end) at minute granularity, end < start wraps midnight, "
                "windows must not overlap. NULL/[] = flat pricing (base columns "
                "apply 24/7); a slot overrides all three unit prices while "
                "active. Only meaningful for pricing_unit='per_1m_tokens'."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the column — flat base prices remain, so cost tracking survives."""
    op.drop_column("llm_model_pricing", "time_slots")
