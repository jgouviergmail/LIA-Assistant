"""Price the browser's Dynamic Maps loads on an upgraded instance.

Revision ID: ef46f93d7745
Revises: b6e2d8f4a1c7
Create Date: 2026-10-04 09:00:00.000000

ADR-332 lets a card draw an interactive map in the browser, and admits it only
when the deployment can price it: ``map_load_config`` and ``browser_maps_key``
refuse while ``maps_javascript /dynamicmap`` has no positive price. The price
was added to the seed bundle alone, and an upgraded instance never replays that
bundle (it deletes and rewrites the whole table) -- so production, and every
installation older than the lot, kept the map switched off.

The row travels here, dated like the bundle's own so a fresh install, where
this runs first, lands on the same row. It is added only where the endpoint has
no active row: a price an administrator entered stands, as every tariff
migration of this repository has it. A guard holds every Maps price the bundle
dated after the 2026-09-23 audit equal to a migration's.
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
revision: str = "ef46f93d7745"
down_revision: str | None = "b6e2d8f4a1c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: Same instant as the seed bundle's row; asyncpg refuses a string for a
#: ``timestamptz`` parameter, so it is bound as a datetime.
EFFECTIVE_FROM_AT = datetime.fromisoformat("2026-10-03T00:00:00+00:00")


class GooglePrice(NamedTuple):
    """One Maps Platform price, USD per 1000 billable events."""

    api_name: str
    endpoint: str
    sku_name: str
    price: str


#: developers.google.com/maps/billing-and-pricing/pricing, Dynamic Maps (the
#: global list price; free tiers and volume discounts are account-specific).
GOOGLE_PRICES: tuple[GooglePrice, ...] = (
    GooglePrice("maps_javascript", "/dynamicmap", "Dynamic Maps", "7"),
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
    """Add each Dynamic Maps price an instance does not hold yet."""
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
    logger.info("dynamic maps price: %d row(s) added", added)


def downgrade() -> None:
    """Remove the Dynamic Maps price this migration dated."""
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
