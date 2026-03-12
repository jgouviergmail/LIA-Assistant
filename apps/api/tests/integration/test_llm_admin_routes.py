"""
Integration tests for LLM Admin API routes.

Tests CRUD operations on model pricing and currency rates with authentication.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.models import User
from src.domains.llm.models import CurrencyExchangeRate, LLMModelPricing

# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def sample_pricing(async_session: AsyncSession) -> LLMModelPricing:
    """Create sample pricing for testing."""
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
    """Create sample currency rate for testing."""
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
# GET /admin/llm/pricing - List Pricing
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_pricing_as_admin(
    admin_client: tuple[AsyncClient, User], sample_pricing: LLMModelPricing
):
    """Test admin can list all active pricing."""
    client, _ = admin_client

    response = await client.get("/api/v1/admin/llm/pricing")

    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert len(data["models"]) == 1
    assert data["models"][0]["model_name"] == "gpt-4.1-mini"
    assert Decimal(data["models"][0]["input_price_per_1m_tokens"]) == Decimal("2.50")
    assert Decimal(data["models"][0]["cached_input_price_per_1m_tokens"]) == Decimal("1.25")
    assert Decimal(data["models"][0]["output_price_per_1m_tokens"]) == Decimal("10.00")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_pricing_as_regular_user_forbidden(
    authenticated_client: tuple[AsyncClient, User],
):
    """Test regular user cannot list pricing (403 Forbidden)."""
    client, _ = authenticated_client

    response = await client.get("/api/v1/admin/llm/pricing")

    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()  # "Admin privileges required"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_pricing_unauthenticated(async_client: AsyncClient):
    """Test unauthenticated user cannot list pricing (401 Unauthorized)."""
    response = await async_client.get("/api/v1/admin/llm/pricing")

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_pricing_empty(admin_client: tuple[AsyncClient, User]):
    """Test listing pricing when database is empty."""
    client, _ = admin_client

    response = await client.get("/api/v1/admin/llm/pricing")

    assert response.status_code == 200
    data = response.json()
    assert data["models"] == []


# ============================================================================
# POST /admin/llm/pricing - Create Pricing
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_pricing_as_admin(
    admin_client: tuple[AsyncClient, User], async_session: AsyncSession
):
    """Test admin can create new pricing entry."""
    client, _ = admin_client

    payload = {
        "model_name": "gpt-4.1-mini",
        "input_price_per_1m_tokens": "0.15",
        "cached_input_price_per_1m_tokens": "0.075",
        "output_price_per_1m_tokens": "0.60",
    }

    response = await client.post("/api/v1/admin/llm/pricing", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["model_name"] == "gpt-4.1-mini"
    assert Decimal(data["input_price_per_1m_tokens"]) == Decimal("0.15")
    assert Decimal(data["cached_input_price_per_1m_tokens"]) == Decimal("0.075")
    assert Decimal(data["output_price_per_1m_tokens"]) == Decimal("0.60")
    assert data["is_active"] is True

    # Verify in database
    stmt = select(LLMModelPricing).where(LLMModelPricing.model_name == "gpt-4.1-mini")
    result = await async_session.execute(stmt)
    pricing = result.scalar_one()
    assert pricing.input_price_per_1m_tokens == Decimal("0.15")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_pricing_without_cached_input(
    admin_client: tuple[AsyncClient, User], async_session: AsyncSession
):
    """Test creating pricing without cached input support."""
    client, _ = admin_client

    payload = {
        "model_name": "o1-mini",
        "input_price_per_1m_tokens": "3.00",
        "cached_input_price_per_1m_tokens": None,
        "output_price_per_1m_tokens": "12.00",
    }

    response = await client.post("/api/v1/admin/llm/pricing", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["model_name"] == "o1-mini"
    assert data["cached_input_price_per_1m_tokens"] is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_pricing_duplicate_model(
    admin_client: tuple[AsyncClient, User], sample_pricing: LLMModelPricing
):
    """Test creating pricing for existing active model fails."""
    client, _ = admin_client

    payload = {
        "model_name": "gpt-4.1-mini",  # Already exists
        "input_price_per_1m_tokens": "2.50",
        "cached_input_price_per_1m_tokens": "1.25",
        "output_price_per_1m_tokens": "10.00",
    }

    response = await client.post("/api/v1/admin/llm/pricing", json=payload)

    assert response.status_code == 409  # Conflict
    assert "already exists" in response.json()["detail"].lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_pricing_invalid_data(admin_client: tuple[AsyncClient, User]):
    """Test creating pricing with invalid data fails validation."""
    client, _ = admin_client

    payload = {
        "model_name": "",  # Empty model name
        "input_price_per_1m_tokens": "2.50",
        "output_price_per_1m_tokens": "10.00",
    }

    response = await client.post("/api/v1/admin/llm/pricing", json=payload)

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_pricing_as_regular_user_forbidden(
    authenticated_client: tuple[AsyncClient, User],
):
    """Test regular user cannot create pricing."""
    client, _ = authenticated_client

    payload = {
        "model_name": "test-model",
        "input_price_per_1m_tokens": "1.00",
        "output_price_per_1m_tokens": "5.00",
    }

    response = await client.post("/api/v1/admin/llm/pricing", json=payload)

    assert response.status_code == 403


# ============================================================================
# PUT /admin/llm/pricing/{model_name} - Update Pricing
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_pricing_as_admin(
    admin_client: tuple[AsyncClient, User],
    sample_pricing: LLMModelPricing,
    async_session: AsyncSession,
):
    """Test admin can update pricing (creates new version, deactivates old)."""
    client, _ = admin_client

    payload = {
        "input_price_per_1m_tokens": "3.00",  # Updated price
        "cached_input_price_per_1m_tokens": "1.50",
        "output_price_per_1m_tokens": "12.00",
    }

    response = await client.put("/api/v1/admin/llm/pricing/gpt-4.1-mini", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["model_name"] == "gpt-4.1-mini"
    assert Decimal(data["input_price_per_1m_tokens"]) == Decimal("3.00")
    assert Decimal(data["output_price_per_1m_tokens"]) == Decimal("12.00")
    assert data["is_active"] is True

    # Verify old entry is deactivated
    await async_session.refresh(sample_pricing)
    assert sample_pricing.is_active is False

    # Verify new entry exists
    stmt = select(LLMModelPricing).where(
        LLMModelPricing.model_name == "gpt-4.1-mini",
        LLMModelPricing.is_active == True,  # noqa: E712
    )
    result = await async_session.execute(stmt)
    new_pricing = result.scalar_one()
    assert new_pricing.id != sample_pricing.id
    assert new_pricing.input_price_per_1m_tokens == Decimal("3.00")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_pricing_not_found(admin_client: tuple[AsyncClient, User]):
    """Test updating non-existent pricing returns 404."""
    client, _ = admin_client

    payload = {
        "input_price_per_1m_tokens": "1.00",
        "output_price_per_1m_tokens": "5.00",
    }

    response = await client.put("/api/v1/admin/llm/pricing/non-existent-model", json=payload)

    assert response.status_code == 404
    assert "found" in response.json()["detail"].lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_pricing_as_regular_user_forbidden(
    authenticated_client: tuple[AsyncClient, User],
):
    """Test regular user cannot update pricing."""
    client, _ = authenticated_client

    payload = {
        "input_price_per_1m_tokens": "1.00",
        "output_price_per_1m_tokens": "5.00",
    }

    response = await client.put("/api/v1/admin/llm/pricing/gpt-4.1-mini", json=payload)

    assert response.status_code == 403


# ============================================================================
# DELETE /admin/llm/pricing/{pricing_id} - Deactivate Pricing
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_deactivate_pricing_as_admin(
    admin_client: tuple[AsyncClient, User],
    sample_pricing: LLMModelPricing,
    async_session: AsyncSession,
):
    """Test admin can deactivate pricing entry."""
    client, _ = admin_client

    response = await client.delete(f"/api/v1/admin/llm/pricing/{sample_pricing.id}")

    assert response.status_code == 204  # No Content

    # Verify in database
    await async_session.refresh(sample_pricing)
    assert sample_pricing.is_active is False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_deactivate_pricing_not_found(admin_client: tuple[AsyncClient, User]):
    """Test deactivating non-existent pricing returns 404."""
    client, _ = admin_client

    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = await client.delete(f"/api/v1/admin/llm/pricing/{fake_uuid}")

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
async def test_deactivate_pricing_as_regular_user_forbidden(
    authenticated_client: tuple[AsyncClient, User], sample_pricing: LLMModelPricing
):
    """Test regular user cannot deactivate pricing."""
    client, _ = authenticated_client

    response = await client.delete(f"/api/v1/admin/llm/pricing/{sample_pricing.id}")

    assert response.status_code == 403


# ============================================================================
# GET /admin/llm/currencies - List Currency Rates
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_currencies_as_admin(
    admin_client: tuple[AsyncClient, User], sample_currency_rate: CurrencyExchangeRate
):
    """Test admin can list all active currency rates."""
    client, _ = admin_client

    response = await client.get("/api/v1/admin/llm/currencies")

    assert response.status_code == 200
    data = response.json()
    assert "rates" in data
    assert len(data["rates"]) == 1
    assert data["rates"][0]["from_currency"] == "USD"
    assert data["rates"][0]["to_currency"] == "EUR"
    assert Decimal(data["rates"][0]["rate"]) == Decimal("0.95")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_currencies_as_regular_user_forbidden(
    authenticated_client: tuple[AsyncClient, User],
):
    """Test regular user cannot list currency rates."""
    client, _ = authenticated_client

    response = await client.get("/api/v1/admin/llm/currencies")

    assert response.status_code == 403


# ============================================================================
# POST /admin/llm/currencies - Create/Update Currency Rate
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_currency_rate_as_admin(
    admin_client: tuple[AsyncClient, User], async_session: AsyncSession
):
    """Test admin can create new currency rate."""
    client, _ = admin_client

    payload = {
        "from_currency": "USD",
        "to_currency": "GBP",
        "rate": "0.79",
    }

    response = await client.post("/api/v1/admin/llm/currencies", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["from_currency"] == "USD"
    assert data["to_currency"] == "GBP"
    assert Decimal(data["rate"]) == Decimal("0.79")
    assert data["is_active"] is True

    # Verify in database
    stmt = select(CurrencyExchangeRate).where(
        CurrencyExchangeRate.from_currency == "USD",
        CurrencyExchangeRate.to_currency == "GBP",
    )
    result = await async_session.execute(stmt)
    rate = result.scalar_one()
    assert rate.rate == Decimal("0.79")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_currency_rate_as_admin(
    admin_client: tuple[AsyncClient, User],
    sample_currency_rate: CurrencyExchangeRate,
    async_session: AsyncSession,
):
    """Test admin can update existing currency rate (creates new version)."""
    client, _ = admin_client

    payload = {
        "from_currency": "USD",
        "to_currency": "EUR",
        "rate": "0.93",  # Updated rate
    }

    response = await client.post("/api/v1/admin/llm/currencies", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert Decimal(data["rate"]) == Decimal("0.93")

    # Verify old entry is deactivated
    await async_session.refresh(sample_currency_rate)
    assert sample_currency_rate.is_active is False

    # Verify new entry exists
    stmt = select(CurrencyExchangeRate).where(
        CurrencyExchangeRate.from_currency == "USD",
        CurrencyExchangeRate.to_currency == "EUR",
        CurrencyExchangeRate.is_active == True,  # noqa: E712
    )
    result = await async_session.execute(stmt)
    new_rate = result.scalar_one()
    assert new_rate.id != sample_currency_rate.id
    assert new_rate.rate == Decimal("0.93")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_currency_rate_invalid_currency_code(admin_client: tuple[AsyncClient, User]):
    """Test creating currency rate with invalid currency code fails."""
    client, _ = admin_client

    payload = {
        "from_currency": "INVALID",  # Too long
        "to_currency": "EUR",
        "rate": "0.95",
    }

    response = await client.post("/api/v1/admin/llm/currencies", json=payload)

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_currency_rate_as_regular_user_forbidden(
    authenticated_client: tuple[AsyncClient, User],
):
    """Test regular user cannot create currency rate."""
    client, _ = authenticated_client

    payload = {
        "from_currency": "USD",
        "to_currency": "GBP",
        "rate": "0.79",
    }

    response = await client.post("/api/v1/admin/llm/currencies", json=payload)

    assert response.status_code == 403


# ============================================================================
# EDGE CASES
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_pricing_shows_only_active(
    admin_client: tuple[AsyncClient, User], async_session: AsyncSession
):
    """Test listing pricing shows only active entries."""
    client, _ = admin_client

    # Create active and inactive pricing
    active = LLMModelPricing(
        model_name="active-model",
        input_price_per_1m_tokens=Decimal("1.00"),
        cached_input_price_per_1m_tokens=None,
        output_price_per_1m_tokens=Decimal("5.00"),
        effective_from=datetime.now(UTC),
        is_active=True,
    )
    inactive = LLMModelPricing(
        model_name="inactive-model",
        input_price_per_1m_tokens=Decimal("2.00"),
        cached_input_price_per_1m_tokens=None,
        output_price_per_1m_tokens=Decimal("10.00"),
        effective_from=datetime.now(UTC),
        is_active=False,
    )
    async_session.add(active)
    async_session.add(inactive)
    await async_session.commit()

    response = await client.get("/api/v1/admin/llm/pricing")

    assert response.status_code == 200
    data = response.json()
    assert len(data["models"]) == 1
    assert data["models"][0]["model_name"] == "active-model"


# ============================================================================
# PAGINATION, SEARCH, AND SORTING TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_pricing_with_pagination(
    admin_client: tuple[AsyncClient, User], async_session: AsyncSession
):
    """Test pagination works correctly with page_size and page parameters."""
    client, _ = admin_client

    # Create 15 models to test pagination
    models = []
    for i in range(15):
        model = LLMModelPricing(
            model_name=f"model-{i:02d}",
            input_price_per_1m_tokens=Decimal(f"{i}.50"),
            cached_input_price_per_1m_tokens=None,
            output_price_per_1m_tokens=Decimal(f"{i * 2}.00"),
            effective_from=datetime.now(UTC),
            is_active=True,
        )
        models.append(model)
        async_session.add(model)
    await async_session.commit()

    # Test first page (default page_size=10)
    response = await client.get("/api/v1/admin/llm/pricing?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 15
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert data["total_pages"] == 2
    assert len(data["models"]) == 10

    # Test second page
    response = await client.get("/api/v1/admin/llm/pricing?page=2&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert len(data["models"]) == 5  # Remaining models


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_pricing_with_search(
    admin_client: tuple[AsyncClient, User], async_session: AsyncSession
):
    """Test search filter by model name."""
    client, _ = admin_client

    # Create models with different names
    gpt_model = LLMModelPricing(
        model_name="gpt-4.1-mini",
        input_price_per_1m_tokens=Decimal("2.50"),
        cached_input_price_per_1m_tokens=None,
        output_price_per_1m_tokens=Decimal("10.00"),
        effective_from=datetime.now(UTC),
        is_active=True,
    )
    claude_model = LLMModelPricing(
        model_name="claude-3.5-sonnet",
        input_price_per_1m_tokens=Decimal("3.00"),
        cached_input_price_per_1m_tokens=None,
        output_price_per_1m_tokens=Decimal("15.00"),
        effective_from=datetime.now(UTC),
        is_active=True,
    )
    o1_model = LLMModelPricing(
        model_name="o1-mini",
        input_price_per_1m_tokens=Decimal("3.00"),
        cached_input_price_per_1m_tokens=None,
        output_price_per_1m_tokens=Decimal("12.00"),
        effective_from=datetime.now(UTC),
        is_active=True,
    )
    async_session.add_all([gpt_model, claude_model, o1_model])
    await async_session.commit()

    # Search for "gpt"
    response = await client.get("/api/v1/admin/llm/pricing?search=gpt")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["models"][0]["model_name"] == "gpt-4.1-mini"

    # Search for "claude" (case-insensitive)
    response = await client.get("/api/v1/admin/llm/pricing?search=CLAUDE")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["models"][0]["model_name"] == "claude-3.5-sonnet"

    # Search with no results
    response = await client.get("/api/v1/admin/llm/pricing?search=nonexistent")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["models"] == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_pricing_with_sorting(
    admin_client: tuple[AsyncClient, User], async_session: AsyncSession
):
    """Test sorting by different columns and orders."""
    client, _ = admin_client

    # Create models with different prices
    model_a = LLMModelPricing(
        model_name="model-a",
        input_price_per_1m_tokens=Decimal("3.00"),
        cached_input_price_per_1m_tokens=None,
        output_price_per_1m_tokens=Decimal("15.00"),
        effective_from=datetime.now(UTC),
        is_active=True,
    )
    model_b = LLMModelPricing(
        model_name="model-b",
        input_price_per_1m_tokens=Decimal("1.00"),
        cached_input_price_per_1m_tokens=None,
        output_price_per_1m_tokens=Decimal("5.00"),
        effective_from=datetime.now(UTC),
        is_active=True,
    )
    model_c = LLMModelPricing(
        model_name="model-c",
        input_price_per_1m_tokens=Decimal("2.00"),
        cached_input_price_per_1m_tokens=None,
        output_price_per_1m_tokens=Decimal("10.00"),
        effective_from=datetime.now(UTC),
        is_active=True,
    )
    async_session.add_all([model_a, model_b, model_c])
    await async_session.commit()

    # Sort by model_name ascending
    response = await client.get("/api/v1/admin/llm/pricing?sort_by=model_name&sort_order=asc")
    assert response.status_code == 200
    data = response.json()
    assert data["models"][0]["model_name"] == "model-a"
    assert data["models"][1]["model_name"] == "model-b"
    assert data["models"][2]["model_name"] == "model-c"

    # Sort by model_name descending
    response = await client.get("/api/v1/admin/llm/pricing?sort_by=model_name&sort_order=desc")
    assert response.status_code == 200
    data = response.json()
    assert data["models"][0]["model_name"] == "model-c"
    assert data["models"][1]["model_name"] == "model-b"
    assert data["models"][2]["model_name"] == "model-a"

    # Sort by input_price_per_1m_tokens ascending
    response = await client.get(
        "/api/v1/admin/llm/pricing?sort_by=input_price_per_1m_tokens&sort_order=asc"
    )
    assert response.status_code == 200
    data = response.json()
    assert Decimal(data["models"][0]["input_price_per_1m_tokens"]) == Decimal("1.00")
    assert Decimal(data["models"][1]["input_price_per_1m_tokens"]) == Decimal("2.00")
    assert Decimal(data["models"][2]["input_price_per_1m_tokens"]) == Decimal("3.00")

    # Sort by output_price_per_1m_tokens descending
    response = await client.get(
        "/api/v1/admin/llm/pricing?sort_by=output_price_per_1m_tokens&sort_order=desc"
    )
    assert response.status_code == 200
    data = response.json()
    assert Decimal(data["models"][0]["output_price_per_1m_tokens"]) == Decimal("15.00")
    assert Decimal(data["models"][1]["output_price_per_1m_tokens"]) == Decimal("10.00")
    assert Decimal(data["models"][2]["output_price_per_1m_tokens"]) == Decimal("5.00")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_pricing_with_combined_filters(
    admin_client: tuple[AsyncClient, User], async_session: AsyncSession
):
    """Test combining search, pagination, and sorting."""
    client, _ = admin_client

    # Create multiple GPT models
    for i in range(5):
        model = LLMModelPricing(
            model_name=f"gpt-{i}",
            input_price_per_1m_tokens=Decimal(f"{i}.00"),
            cached_input_price_per_1m_tokens=None,
            output_price_per_1m_tokens=Decimal(f"{i * 5}.00"),
            effective_from=datetime.now(UTC),
            is_active=True,
        )
        async_session.add(model)

    # Create Claude models
    for i in range(3):
        model = LLMModelPricing(
            model_name=f"claude-{i}",
            input_price_per_1m_tokens=Decimal(f"{i + 10}.00"),
            cached_input_price_per_1m_tokens=None,
            output_price_per_1m_tokens=Decimal(f"{i * 10}.00"),
            effective_from=datetime.now(UTC),
            is_active=True,
        )
        async_session.add(model)

    await async_session.commit()

    # Search for "gpt", sort by input_price descending, paginate with page_size=3
    response = await client.get(
        "/api/v1/admin/llm/pricing?search=gpt&sort_by=input_price_per_1m_tokens&sort_order=desc&page=1&page_size=3"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5  # 5 GPT models found
    assert data["page"] == 1
    assert data["page_size"] == 3
    assert data["total_pages"] == 2
    assert len(data["models"]) == 3
    # Verify descending order
    assert Decimal(data["models"][0]["input_price_per_1m_tokens"]) >= Decimal(
        data["models"][1]["input_price_per_1m_tokens"]
    )
    assert Decimal(data["models"][1]["input_price_per_1m_tokens"]) >= Decimal(
        data["models"][2]["input_price_per_1m_tokens"]
    )
