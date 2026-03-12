"""
Pydantic schemas for Google API tracking domain.

Schemas:
- GoogleApiPricingResponse: Pricing data for API responses
- GoogleApiPricingCreate: Request for creating new pricing entry
- GoogleApiPricingUpdate: Request for updating pricing entry
- GoogleApiPricingListResponse: Paginated list of pricing entries
- GoogleApiUsageResponse: Usage log data for API responses

Author: Claude Code (Opus 4.5)
Date: 2026-02-04
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GoogleApiPricingResponse(BaseModel):
    """Pricing configuration data for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    api_name: str
    endpoint: str
    sku_name: str
    cost_per_1000_usd: Decimal
    effective_from: datetime
    is_active: bool


class GoogleApiPricingCreate(BaseModel):
    """Request model for creating new Google API pricing entry."""

    api_name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="API identifier (places, routes, geocoding, static_maps)",
    )
    endpoint: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Endpoint path (e.g., /places:searchText)",
    )
    sku_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Google SKU name (e.g., Text Search Pro)",
    )
    cost_per_1000_usd: Decimal = Field(
        ...,
        gt=0,
        description="Cost per 1000 requests in USD",
    )


class GoogleApiPricingUpdate(BaseModel):
    """Request model for updating Google API pricing (creates new active entry).

    Note: api_name and endpoint are optional. If provided, they will rename the entry.
    Uniqueness is validated server-side.
    """

    api_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="New API identifier (optional, for renaming)",
    )
    endpoint: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="New endpoint path (optional, for renaming)",
    )
    sku_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Google SKU name (e.g., Text Search Pro)",
    )
    cost_per_1000_usd: Decimal = Field(
        ...,
        gt=0,
        description="Cost per 1000 requests in USD",
    )


class GoogleApiPricingListResponse(BaseModel):
    """Response model for listing all active Google API pricing with pagination."""

    total: int
    page: int
    page_size: int
    total_pages: int
    entries: list[GoogleApiPricingResponse]


class GoogleApiUsageResponse(BaseModel):
    """Usage log data for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    run_id: str
    api_name: str
    endpoint: str
    request_count: int
    cost_usd: Decimal
    cost_eur: Decimal
    cached: bool
    created_at: datetime
