"""Add Google API tracking system.

Revision ID: add_google_api_tracking_001
Revises: migrate_places_api_key_001
Create Date: 2026-02-04

This migration creates the Google API tracking system:

1. google_api_pricing table:
   - Stores cost per 1000 requests for each API endpoint
   - Supports historical pricing with effective_from date

2. google_api_usage_logs table:
   - Audit trail for each Google API call
   - Links to MessageTokenSummary via run_id

3. message_token_summary columns:
   - google_api_requests: Count of Google API calls per message
   - google_api_cost_eur: Cost of Google API calls per message

4. user_statistics columns:
   - total_google_api_requests: Lifetime Google API calls
   - total_google_api_cost_eur: Lifetime Google API cost
   - cycle_google_api_requests: Current cycle Google API calls
   - cycle_google_api_cost_eur: Current cycle Google API cost

5. Seed data for Google Maps Platform pricing (2026 rates).
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_google_api_tracking_001"
down_revision: str | None = "migrate_places_api_key_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add Google API tracking: pricing table, usage logs, and statistics columns.
    """
    # =========================================================================
    # 1. Create google_api_pricing table
    # =========================================================================
    op.create_table(
        "google_api_pricing",
        # Primary key
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # API identification
        sa.Column(
            "api_name",
            sa.String(50),
            nullable=False,
            comment="API identifier: places, routes, geocoding, static_maps",
        ),
        sa.Column(
            "endpoint",
            sa.String(100),
            nullable=False,
            comment="Endpoint path: /places:searchText, etc.",
        ),
        sa.Column(
            "sku_name",
            sa.String(100),
            nullable=False,
            comment="Google SKU name: Text Search Pro, etc.",
        ),
        # Pricing
        sa.Column(
            "cost_per_1000_usd",
            sa.Numeric(10, 4),
            nullable=False,
            comment="Cost per 1000 requests in USD",
        ),
        # Validity
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Date when this pricing became effective",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Whether this pricing is currently active",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Indexes for google_api_pricing
    op.create_index(
        "ix_google_api_pricing_api_name",
        "google_api_pricing",
        ["api_name"],
    )
    op.create_index(
        "ix_google_api_pricing_endpoint",
        "google_api_pricing",
        ["endpoint"],
    )
    op.create_index(
        "ix_google_api_pricing_is_active",
        "google_api_pricing",
        ["is_active"],
    )
    op.create_index(
        "ix_google_api_pricing_lookup",
        "google_api_pricing",
        ["api_name", "endpoint", "is_active"],
    )

    # =========================================================================
    # 2. Create google_api_usage_logs table
    # =========================================================================
    op.create_table(
        "google_api_usage_logs",
        # Primary key
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Foreign key to users
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Tracking linkage
        sa.Column(
            "run_id",
            sa.String(255),
            nullable=False,
            comment="LangGraph run_id (links to message_token_summary) or synthetic ID for non-chat calls",
        ),
        # API identification
        sa.Column(
            "api_name",
            sa.String(50),
            nullable=False,
            comment="API identifier: places, routes, geocoding, static_maps",
        ),
        sa.Column(
            "endpoint",
            sa.String(100),
            nullable=False,
            comment="Endpoint called",
        ),
        # Usage metrics
        sa.Column(
            "request_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Number of requests (usually 1, can be batch)",
        ),
        # Cost tracking
        sa.Column(
            "cost_usd",
            sa.Numeric(10, 6),
            nullable=False,
            comment="Cost in USD for this call",
        ),
        sa.Column(
            "cost_eur",
            sa.Numeric(10, 6),
            nullable=False,
            comment="Cost in EUR for this call",
        ),
        sa.Column(
            "usd_to_eur_rate",
            sa.Numeric(10, 6),
            nullable=False,
            comment="Exchange rate used for conversion (for audit)",
        ),
        # Cache indicator
        sa.Column(
            "cached",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether result was served from cache (no cost)",
        ),
        # Timestamps (BaseModel includes both via TimestampMixin)
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Indexes for google_api_usage_logs
    op.create_index(
        "ix_google_api_usage_logs_user_id",
        "google_api_usage_logs",
        ["user_id"],
    )
    op.create_index(
        "ix_google_api_usage_logs_run_id",
        "google_api_usage_logs",
        ["run_id"],
    )
    op.create_index(
        "ix_google_api_usage_user_date",
        "google_api_usage_logs",
        ["user_id", "created_at"],
    )

    # =========================================================================
    # 3. Add Google API columns to message_token_summary
    # =========================================================================
    op.add_column(
        "message_token_summary",
        sa.Column(
            "google_api_requests",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of Google API calls for this message",
        ),
    )
    op.add_column(
        "message_token_summary",
        sa.Column(
            "google_api_cost_eur",
            sa.Numeric(10, 6),
            nullable=False,
            server_default="0",
            comment="Cost of Google API calls in EUR for this message",
        ),
    )

    # =========================================================================
    # 4. Add Google API columns to user_statistics
    # =========================================================================
    # Lifetime totals
    op.add_column(
        "user_statistics",
        sa.Column(
            "total_google_api_requests",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="All-time Google API calls",
        ),
    )
    op.add_column(
        "user_statistics",
        sa.Column(
            "total_google_api_cost_eur",
            sa.Numeric(12, 6),
            nullable=False,
            server_default="0",
            comment="All-time Google API cost in EUR",
        ),
    )
    # Current billing cycle
    op.add_column(
        "user_statistics",
        sa.Column(
            "cycle_google_api_requests",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="Google API calls this cycle",
        ),
    )
    op.add_column(
        "user_statistics",
        sa.Column(
            "cycle_google_api_cost_eur",
            sa.Numeric(12, 6),
            nullable=False,
            server_default="0",
            comment="Google API cost in EUR this cycle",
        ),
    )

    # =========================================================================
    # 5. Seed Google Maps Platform pricing data
    # =========================================================================
    _seed_google_api_pricing()


def _seed_google_api_pricing() -> None:
    """Seed Google Maps Platform pricing data."""
    now = datetime.now(UTC)
    conn = op.get_bind()

    # Google Maps Platform pricing (2026 rates)
    # Source: https://mapsplatform.google.com/pricing/
    # Prices in USD per 1000 requests
    pricing_data = [
        # Places API
        {
            "api_name": "places",
            "endpoint": "/places:searchText",
            "sku_name": "Text Search Pro",
            "cost_per_1000_usd": 32.0000,
        },
        {
            "api_name": "places",
            "endpoint": "/places:searchNearby",
            "sku_name": "Nearby Search Pro",
            "cost_per_1000_usd": 32.0000,
        },
        {
            "api_name": "places",
            "endpoint": "/places/{id}",
            "sku_name": "Place Details Pro",
            "cost_per_1000_usd": 17.0000,
        },
        {
            "api_name": "places",
            "endpoint": "/places:autocomplete",
            "sku_name": "Autocomplete",
            "cost_per_1000_usd": 2.8300,
        },
        {
            "api_name": "places",
            "endpoint": "/{photo}/media",
            "sku_name": "Place Photos",
            "cost_per_1000_usd": 7.0000,
        },
        # Routes API
        {
            "api_name": "routes",
            "endpoint": "/directions/v2:computeRoutes",
            "sku_name": "Compute Routes",
            "cost_per_1000_usd": 5.0000,
        },
        {
            "api_name": "routes",
            "endpoint": "/distanceMatrix/v2:computeRouteMatrix",
            "sku_name": "Route Matrix",
            "cost_per_1000_usd": 5.0000,
        },
        # Geocoding API
        {
            "api_name": "geocoding",
            "endpoint": "/geocode/json",
            "sku_name": "Geocoding",
            "cost_per_1000_usd": 5.0000,
        },
        # Static Maps API
        {
            "api_name": "static_maps",
            "endpoint": "/staticmap",
            "sku_name": "Static Maps",
            "cost_per_1000_usd": 2.0000,
        },
    ]

    for pricing in pricing_data:
        conn.execute(
            sa.text("""
                INSERT INTO google_api_pricing (
                    id,
                    api_name,
                    endpoint,
                    sku_name,
                    cost_per_1000_usd,
                    effective_from,
                    is_active,
                    created_at,
                    updated_at
                ) VALUES (
                    gen_random_uuid(),
                    :api_name,
                    :endpoint,
                    :sku_name,
                    :cost_per_1000_usd,
                    :effective_from,
                    true,
                    :created_at,
                    :updated_at
                )
            """),
            {
                "api_name": pricing["api_name"],
                "endpoint": pricing["endpoint"],
                "sku_name": pricing["sku_name"],
                "cost_per_1000_usd": pricing["cost_per_1000_usd"],
                "effective_from": now,
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    """
    Remove Google API tracking system.
    """
    # Drop user_statistics columns
    op.drop_column("user_statistics", "cycle_google_api_cost_eur")
    op.drop_column("user_statistics", "cycle_google_api_requests")
    op.drop_column("user_statistics", "total_google_api_cost_eur")
    op.drop_column("user_statistics", "total_google_api_requests")

    # Drop message_token_summary columns
    op.drop_column("message_token_summary", "google_api_cost_eur")
    op.drop_column("message_token_summary", "google_api_requests")

    # Drop google_api_usage_logs indexes and table
    op.drop_index("ix_google_api_usage_user_date", table_name="google_api_usage_logs")
    op.drop_index("ix_google_api_usage_logs_run_id", table_name="google_api_usage_logs")
    op.drop_index("ix_google_api_usage_logs_user_id", table_name="google_api_usage_logs")
    op.drop_table("google_api_usage_logs")

    # Drop google_api_pricing indexes and table
    op.drop_index("ix_google_api_pricing_lookup", table_name="google_api_pricing")
    op.drop_index("ix_google_api_pricing_is_active", table_name="google_api_pricing")
    op.drop_index("ix_google_api_pricing_endpoint", table_name="google_api_pricing")
    op.drop_index("ix_google_api_pricing_api_name", table_name="google_api_pricing")
    op.drop_table("google_api_pricing")
