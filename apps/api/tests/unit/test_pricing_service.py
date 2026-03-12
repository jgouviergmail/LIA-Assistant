"""
Unit tests for Async LLM Pricing Service.

Tests async pricing service with caching, TTL, and error handling.
"""

import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.models import CurrencyExchangeRate, LLMModelPricing
from src.domains.llm.pricing_service import AsyncPricingService, ModelPrice

# Skip in pre-commit - uses testcontainers/real DB, too slow
# Run manually with: pytest tests/unit/test_pricing_service.py -v
pytestmark = pytest.mark.integration

# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def sample_pricing_gpt4o(async_session: AsyncSession) -> LLMModelPricing:
    """Create sample gpt-4.1-mini pricing entry (async)."""
    pricing = LLMModelPricing(
        model_name="gpt-4.1-mini",
        input_price_per_1m_tokens=Decimal("2.50"),
        cached_input_price_per_1m_tokens=Decimal("1.25"),
        output_price_per_1m_tokens=Decimal("10.00"),
        effective_from=datetime.now(UTC),
        is_active=True,
    )
    async_session.add(pricing)
    await async_session.commit()
    await async_session.refresh(pricing)
    return pricing


@pytest_asyncio.fixture
async def sample_currency_rate(async_session: AsyncSession) -> CurrencyExchangeRate:
    """Create sample USD/EUR currency rate (async)."""
    rate = CurrencyExchangeRate(
        from_currency="USD",
        to_currency="EUR",
        rate=Decimal("0.95"),
        effective_from=datetime.now(UTC),
        is_active=True,
    )
    async_session.add(rate)
    await async_session.commit()
    await async_session.refresh(rate)
    return rate


# ============================================================================
# ASYNC PRICING SERVICE TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_active_model_price_found(
    async_session: AsyncSession, sample_pricing_gpt4o: LLMModelPricing
):
    """Test retrieving active model pricing successfully (async)."""
    service = AsyncPricingService(db=async_session)

    price = await service.get_active_model_price("gpt-4.1-mini")

    assert price is not None
    assert isinstance(price, ModelPrice)
    assert price.model_name == "gpt-4.1-mini"
    assert price.input_price == Decimal("2.50")
    assert price.cached_input_price == Decimal("1.25")
    assert price.output_price == Decimal("10.00")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_active_model_price_not_found(async_session: AsyncSession):
    """Test retrieving non-existent model pricing returns None."""
    service = AsyncPricingService(db=async_session)

    price = await service.get_active_model_price("non-existent-model")

    assert price is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_active_currency_rate_found(
    async_session: AsyncSession, sample_currency_rate: CurrencyExchangeRate
):
    """Test retrieving active currency rate successfully."""
    service = AsyncPricingService(db=async_session)

    rate = await service.get_active_currency_rate("USD", "EUR")

    assert rate == Decimal("0.95")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_active_currency_rate_not_found(async_session: AsyncSession):
    """Test retrieving non-existent currency rate raises ValueError."""
    service = AsyncPricingService(db=async_session)

    with pytest.raises(ValueError, match="Currency rate not found: USD/GBP"):
        await service.get_active_currency_rate("USD", "GBP")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cache_expiry(async_session: AsyncSession, sample_pricing_gpt4o: LLMModelPricing):
    """Test that pricing cache expires after TTL."""
    service = AsyncPricingService(db=async_session, cache_ttl_seconds=1)

    # First call
    price1 = await service.get_active_model_price("gpt-4.1-mini")
    assert price1 is not None

    # Wait for cache to expire
    time.sleep(1.5)

    # Second call - cache should be invalidated
    price2 = await service.get_active_model_price("gpt-4.1-mini")
    assert price2 is not None
    assert price1 == price2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_invalidate_all_caches(
    async_session: AsyncSession, sample_pricing_gpt4o: LLMModelPricing
):
    """Test invalidating all caches."""
    service = AsyncPricingService(db=async_session)

    # Populate cache
    price1 = await service.get_active_model_price("gpt-4.1-mini")
    assert price1 is not None

    # Invalidate
    service.invalidate_all_caches()

    # Cache timestamps should be cleared
    assert len(service._cache_timestamp) == 0
