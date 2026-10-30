"""Price the Weather daily forecast the dashboard card now reads.

Revision ID: b2a59e675271
Revises: e5f51d793219
Create Date: 2026-10-29 03:00:00.000000

The weather card read its five-day strip from five hourly pages of
forecast/hours:lookup (24 hours each); it now reads the provider's own daily
summaries from ONE forecast/days:lookup request (spec 2026-10-21 W1b). That
endpoint is billed under the same « Weather Usage » SKU as the two weather rows the
table already holds, and a tracked call with no row is billed at zero. An upgraded
instance never replays the seed bundle, so the price travels here, dated like the
bundle's row; it is added only where the endpoint has no active row — a price an
administrator entered stands.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2a59e675271"
down_revision: str | None = "e5f51d793219"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: Same instant as the seed bundle's row; asyncpg refuses a string for a
#: timestamptz parameter, so it is bound as a datetime.
EFFECTIVE_FROM_AT = datetime.fromisoformat("2026-10-29T00:00:00+00:00")


class GooglePrice(NamedTuple):
    """One Maps Platform price, USD per 1000 billable events."""

    api_name: str
    endpoint: str
    sku_name: str
    price: str


#: developers.google.com/maps/billing-and-pricing/pricing, « Weather Usage » (SKU
#: 9DB8-727A-ACFE: currentConditions, forecast.hours, forecast.days, ...) — the first
#: paid tier's list price, the one the two existing weather rows carry.
GOOGLE_PRICES: tuple[GooglePrice, ...] = (
    GooglePrice("weather", "/v1/forecast/days:lookup", "Weather Daily Forecast", "0.15"),
)

#: Add a price where the endpoint has no active row.
INSERT_GOOGLE = sa.text("""
    INSERT INTO google_api_pricing (
        id, api_name, endpoint, sku_name, cost_per_1000_usd, effective_from,
        is_active, created_at, updated_at
    )
    SELECT gen_random_uuid(), v.api_name, v.endpoint, v.sku_name, v.price,
           v.effective_from, true, NOW(), NOW()
      FROM (VALUES (
           CAST(:api_name AS varchar), CAST(:endpoint AS varchar),
           CAST(:sku_name AS varchar), CAST(:price AS numeric),
           CAST(:effective_from AS timestamptz)
      )) AS v(api_name, endpoint, sku_name, price, effective_from)
     WHERE NOT EXISTS (
           SELECT 1 FROM google_api_pricing p
            WHERE p.api_name = v.api_name AND p.endpoint = v.endpoint AND p.is_active
     )
    """)

#: Downgrade: remove the row this migration added (dated like the bundle).
DELETE_GOOGLE = sa.text("""
    DELETE FROM google_api_pricing
     WHERE api_name = CAST(:api_name AS varchar)
       AND endpoint = CAST(:endpoint AS varchar)
       AND effective_from = CAST(:effective_from AS timestamptz)
    """)


def upgrade() -> None:
    """Add the daily forecast price an instance does not hold yet."""
    bind = op.get_bind()
    added = 0
    for row in GOOGLE_PRICES:
        added += bind.execute(
            INSERT_GOOGLE,
            {
                "api_name": row.api_name,
                "endpoint": row.endpoint,
                "sku_name": row.sku_name,
                "price": Decimal(row.price),
                "effective_from": EFFECTIVE_FROM_AT,
            },
        ).rowcount
    logger.info("weather daily forecast price: %d row(s) added", added)


def downgrade() -> None:
    """Remove the daily forecast price this migration dated."""
    bind = op.get_bind()
    for row in GOOGLE_PRICES:
        bind.execute(
            DELETE_GOOGLE,
            {
                "api_name": row.api_name,
                "endpoint": row.endpoint,
                "effective_from": EFFECTIVE_FROM_AT,
            },
        )
