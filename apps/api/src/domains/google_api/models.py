"""
SQLAlchemy models for Google API tracking domain.

Models:
- GoogleApiPricing: Pricing configuration for Google API endpoints
- GoogleApiUsageLog: Audit trail for Google API calls

Author: Claude Code (Opus 4.5)
Date: 2026-02-04
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class GoogleApiPricing(BaseModel):
    """
    Pricing configuration for Google API endpoints.

    Stores cost per 1000 requests for each Google Maps Platform API endpoint.
    This is a configuration table that can be updated when Google changes pricing.

    Attributes:
        api_name: API identifier (places, routes, geocoding, static_maps)
        endpoint: Endpoint path (e.g., /places:searchText)
        sku_name: Google SKU name (e.g., Text Search Pro)
        cost_per_1000_usd: Cost per 1000 requests in USD
        effective_from: Date when this pricing became effective
        is_active: Whether this pricing is currently active
    """

    __tablename__ = "google_api_pricing"

    # API identification
    api_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    endpoint: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    # Pricing details
    sku_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    cost_per_1000_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
    )

    # Validity
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_google_api_pricing_lookup",
            "api_name",
            "endpoint",
            "is_active",
        ),
    )

    def __repr__(self) -> str:
        return f"<GoogleApiPricing(api={self.api_name}, endpoint={self.endpoint}, cost=${self.cost_per_1000_usd}/1000)>"


class GoogleApiUsageLog(BaseModel):
    """
    Audit trail for Google API calls.

    Records each billable Google API call for cost tracking and user billing.
    Follows TokenUsageLog pattern for consistency (immutable audit records).

    Attributes:
        user_id: User who made the API call
        run_id: LangGraph run ID (links to MessageTokenSummary), or synthetic ID for non-chat calls
        api_name: API identifier (places, routes, geocoding, static_maps)
        endpoint: Endpoint called
        request_count: Number of requests (usually 1, can be batch)
        cost_usd: Cost in USD for this call
        cost_eur: Cost in EUR for this call
        usd_to_eur_rate: Exchange rate used for conversion (for audit)
        cached: Whether result was served from cache (no cost)
    """

    __tablename__ = "google_api_usage_logs"

    # Foreign keys
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Tracking linkage
    run_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    # API identification
    api_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    endpoint: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Usage metrics
    request_count: Mapped[int] = mapped_column(
        nullable=False,
        default=1,
    )

    # Cost tracking
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
    )
    cost_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
    )
    usd_to_eur_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
    )

    # Cache indicator
    cached: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    __table_args__ = (
        Index(
            "ix_google_api_usage_user_date",
            "user_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<GoogleApiUsageLog(user={self.user_id}, api={self.api_name}, cost=${self.cost_usd})>"
        )
