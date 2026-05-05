"""
Pydantic schemas for LLM pricing API.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Enum-like literal type for the provider field. Must stay in sync with
# LLMProviderEnum (apps/api/src/domains/llm/models.py) AND LLM_PROVIDERS
# (apps/api/src/domains/llm_config/constants.py).
ProviderLiteral = Literal[
    "openai",
    "anthropic",
    "deepseek",
    "perplexity",
    "ollama",
    "gemini",
    "qwen",
]


class ModelPriceResponse(BaseModel):
    """Response model for an LLM model + its active pricing.

    Returns both catalogue fields (provider, capabilities) and pricing in a
    flat structure. Built via :func:`router._pricing_to_response` from a
    pricing row whose ``model`` relationship is selectinload'd.
    """

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    # Pricing row identity + pricing fields
    id: uuid.UUID
    input_price_per_1m_tokens: Decimal
    cached_input_price_per_1m_tokens: Decimal | None
    output_price_per_1m_tokens: Decimal
    effective_from: datetime
    is_active: bool

    # Catalogue fields (from llm_models via JOIN)
    provider: ProviderLiteral
    model_name: str
    max_input_tokens: int
    max_output_tokens: int
    supports_tools: bool
    supports_structured_output: bool
    supports_strict_mode: bool
    supports_streaming: bool
    supports_vision: bool
    is_reasoning_model: bool


class ModelPriceCreate(BaseModel):
    """Request model: create a new LLM model + its initial pricing in one transaction.

    The 14-field admin form sends this payload. The service layer
    (``LLMModelService.create``) inserts both an ``llm_models`` row and an
    initial active ``llm_model_pricing`` row pointing to it, atomically.
    """

    model_config = ConfigDict(protected_namespaces=())

    # --- Catalogue ---
    provider: ProviderLiteral = Field(..., description="Provider that hosts this model")
    model_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9._\-/:]+$",
        description="Globally unique model identifier",
    )

    # --- Capabilities ---
    max_input_tokens: int = Field(..., gt=0, description="Maximum context window size")
    max_output_tokens: int = Field(..., ge=0, description="Maximum response tokens")
    supports_tools: bool = Field(..., description="Whether the model supports tool calling")
    supports_structured_output: bool = Field(
        ..., description="Whether the model supports structured output"
    )
    supports_strict_mode: bool = Field(
        ..., description="Whether the model supports strict-mode structured output (OpenAI-only)"
    )
    supports_streaming: bool = Field(..., description="Whether the model supports streaming")
    supports_vision: bool = Field(..., description="Whether the model accepts image inputs")
    is_reasoning_model: bool = Field(
        ..., description="Whether the model is a reasoning model (o-series, GPT-5, ...)"
    )

    # --- Pricing ---
    input_price_per_1m_tokens: Decimal = Field(
        ..., ge=0, description="Price in USD per 1M input tokens"
    )
    cached_input_price_per_1m_tokens: Decimal | None = Field(
        None, ge=0, description="Price in USD per 1M cached input tokens (optional)"
    )
    output_price_per_1m_tokens: Decimal = Field(
        ..., ge=0, description="Price in USD per 1M output tokens"
    )


class ModelPriceUpdate(BaseModel):
    """Request model: partial update of capabilities and/or pricing.

    All fields are optional. ``provider`` is intentionally NOT updatable here
    (it is an intrinsic property of the model). ``model_name`` is updatable —
    it renames the model in place on llm_models.

    The service layer differentiates three cases:
    - capabilities only → mutate llm_models in place
    - pricing only → temporal versioning on llm_model_pricing
    - mixed → both, in a single transaction
    """

    model_config = ConfigDict(protected_namespaces=())

    # --- Catalogue (all optional) ---
    model_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9._\-/:]+$",
        description="Rename to this name (kept on llm_models, no new pricing row)",
    )
    max_input_tokens: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, ge=0)
    supports_tools: bool | None = None
    supports_structured_output: bool | None = None
    supports_strict_mode: bool | None = None
    supports_streaming: bool | None = None
    supports_vision: bool | None = None
    is_reasoning_model: bool | None = None

    # --- Pricing (all optional) ---
    input_price_per_1m_tokens: Decimal | None = Field(default=None, ge=0)
    cached_input_price_per_1m_tokens: Decimal | None = Field(default=None, ge=0)
    output_price_per_1m_tokens: Decimal | None = Field(default=None, ge=0)


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
