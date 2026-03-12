"""
Pydantic schemas for LLM pricing API.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ModelPriceResponse(BaseModel):
    """
    Response model for LLM pricing information.

    Used by PricingService to return pricing data.
    """

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    model_name: str
    input_price_per_1m_tokens: Decimal
    cached_input_price_per_1m_tokens: Decimal | None
    output_price_per_1m_tokens: Decimal
    effective_from: datetime
    is_active: bool


class ModelPriceCreate(BaseModel):
    """Request model for creating new LLM pricing entry."""

    model_config = ConfigDict(protected_namespaces=())

    model_name: str = Field(..., min_length=1, max_length=100, description="LLM model identifier")
    input_price_per_1m_tokens: Decimal = Field(
        ..., gt=0, description="Price in USD per 1M input tokens"
    )
    cached_input_price_per_1m_tokens: Decimal | None = Field(
        None, gt=0, description="Price in USD per 1M cached input tokens"
    )
    output_price_per_1m_tokens: Decimal = Field(
        ..., gt=0, description="Price in USD per 1M output tokens"
    )


class ModelPriceUpdate(BaseModel):
    """Request model for updating LLM pricing (creates new active entry).

    Note: model_name is optional. If provided, it will rename the model.
    Uniqueness is validated server-side.
    """

    model_config = ConfigDict(protected_namespaces=())

    model_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="New LLM model identifier (optional, for renaming)",
    )
    input_price_per_1m_tokens: Decimal = Field(
        ..., gt=0, description="Price in USD per 1M input tokens"
    )
    cached_input_price_per_1m_tokens: Decimal | None = Field(
        None, gt=0, description="Price in USD per 1M cached input tokens"
    )
    output_price_per_1m_tokens: Decimal = Field(
        ..., gt=0, description="Price in USD per 1M output tokens"
    )


class CurrencyRateResponse(BaseModel):
    """Response model for currency exchange rate."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_currency: str
    to_currency: str
    rate: Decimal
    effective_from: datetime
    is_active: bool


class CurrencyRateCreate(BaseModel):
    """Request model for creating new currency exchange rate."""

    from_currency: str = Field(
        ..., min_length=3, max_length=3, description="Source currency code (ISO 4217)"
    )
    to_currency: str = Field(
        ..., min_length=3, max_length=3, description="Target currency code (ISO 4217)"
    )
    rate: Decimal = Field(
        ..., gt=0, description="Exchange rate (1 from_currency = rate to_currency)"
    )


class LLMPricingListResponse(BaseModel):
    """Response model for listing all active LLM pricing with pagination."""

    total: int
    page: int
    page_size: int
    total_pages: int
    models: list[ModelPriceResponse]


class CurrencyRatesListResponse(BaseModel):
    """Response model for listing all active currency rates."""

    total: int
    rates: list[CurrencyRateResponse]
