"""
Unit tests for CurrencyRateService.

Tests API integration with mocked httpx responses.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.infrastructure.external.currency_api import CurrencyRateService


@pytest.fixture(autouse=True)
def _clear_class_caches():
    """Clear class-level caches between tests to avoid cross-test pollution."""
    CurrencyRateService._rate_cache.clear()
    CurrencyRateService._negative_cache.clear()
    yield
    CurrencyRateService._rate_cache.clear()
    CurrencyRateService._negative_cache.clear()


@pytest.mark.asyncio
async def test_get_rate_success():
    """Test successful API call returns rate."""
    service = CurrencyRateService()

    # Mock httpx response
    mock_response = MagicMock()
    mock_response.json.return_value = {"rates": {"EUR": 0.95}}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        rate = await service.get_rate("USD", "EUR")

    assert rate == Decimal("0.95")


@pytest.mark.asyncio
async def test_get_rate_cache_hit():
    """Test cache returns same rate within TTL (no API call)."""
    service = CurrencyRateService()

    # Pre-populate class-level cache with valid entry
    CurrencyRateService._rate_cache["USD_EUR"] = (Decimal("0.95"), datetime.now(UTC))

    # Mock httpx to ensure it's NOT called
    with patch("httpx.AsyncClient.get") as mock_get:
        rate = await service.get_rate("USD", "EUR")

    assert rate == Decimal("0.95")
    # Verify no API call was made
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_get_rate_cache_shared_across_instances():
    """Test cache is shared across different CurrencyRateService instances."""
    service_a = CurrencyRateService()
    service_b = CurrencyRateService()

    # Populate cache via service_a
    mock_response = MagicMock()
    mock_response.json.return_value = {"rates": {"EUR": 0.95}}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        await service_a.get_rate("USD", "EUR")

    # service_b should hit the cache (no API call)
    with patch("httpx.AsyncClient.get") as mock_get:
        rate = await service_b.get_rate("USD", "EUR")

    assert rate == Decimal("0.95")
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_get_rate_cache_expiry():
    """Test cache expires after TTL and fetches new rate."""
    service = CurrencyRateService()

    # Pre-populate cache with EXPIRED entry (25 hours ago)
    expired_time = datetime.now(UTC) - timedelta(hours=25)
    CurrencyRateService._rate_cache["USD_EUR"] = (Decimal("0.90"), expired_time)

    # Mock httpx response with NEW rate
    mock_response = MagicMock()
    mock_response.json.return_value = {"rates": {"EUR": 0.96}}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        rate = await service.get_rate("USD", "EUR")

    # Should return NEW rate from API (not cached 0.90)
    assert rate == Decimal("0.96")
    # Verify cache was updated
    assert CurrencyRateService._rate_cache["USD_EUR"][0] == Decimal("0.96")


@pytest.mark.asyncio
async def test_get_rate_api_http_error():
    """Test API HTTP error returns None and populates negative cache."""
    service = CurrencyRateService()

    with patch("httpx.AsyncClient.get", side_effect=httpx.HTTPError("API unavailable")):
        rate = await service.get_rate("USD", "EUR")

    assert rate is None
    # Negative cache should be populated
    assert "USD_EUR" in CurrencyRateService._negative_cache


@pytest.mark.asyncio
async def test_get_rate_negative_cache_prevents_retry():
    """Test negative cache prevents API retries after failure."""
    service = CurrencyRateService()

    # First call: API fails, populates negative cache
    with patch("httpx.AsyncClient.get", side_effect=httpx.HTTPError("down")) as mock_get:
        rate1 = await service.get_rate("USD", "EUR")
        assert rate1 is None
        first_call_count = mock_get.call_count

    # Second call: should hit negative cache (no API call)
    with patch("httpx.AsyncClient.get") as mock_get:
        rate2 = await service.get_rate("USD", "EUR")
        assert rate2 is None
        mock_get.assert_not_called()

    assert first_call_count > 0  # First call did try the API


@pytest.mark.asyncio
async def test_get_rate_negative_cache_expires():
    """Test negative cache expires and allows retry."""
    service = CurrencyRateService()

    # Pre-populate negative cache with EXPIRED entry (10 min ago, TTL is 5 min)
    CurrencyRateService._negative_cache["USD_EUR"] = datetime.now(UTC) - timedelta(minutes=10)

    # Mock successful API response
    mock_response = MagicMock()
    mock_response.json.return_value = {"rates": {"EUR": 0.95}}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        rate = await service.get_rate("USD", "EUR")

    assert rate == Decimal("0.95")
    mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_get_rate_api_invalid_json():
    """Test API returns invalid JSON (KeyError) returns None."""
    service = CurrencyRateService()

    # Mock httpx response with MISSING rates key
    mock_response = MagicMock()
    mock_response.json.return_value = {"error": "Invalid currency"}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        rate = await service.get_rate("USD", "INVALID")

    assert rate is None


@pytest.mark.asyncio
async def test_get_rate_api_invalid_rate_value():
    """Test API returns non-numeric rate (ValueError) returns None."""
    service = CurrencyRateService()

    # Mock httpx response with NON-NUMERIC rate
    mock_response = MagicMock()
    mock_response.json.return_value = {"rates": {"EUR": "invalid_number"}}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        rate = await service.get_rate("USD", "EUR")

    assert rate is None


@pytest.mark.asyncio
async def test_get_rate_custom_api_url():
    """Test service uses custom API URL if provided."""
    custom_url = "https://custom-currency-api.com"
    service = CurrencyRateService(api_url=custom_url)

    assert service.api_url == custom_url

    # Mock httpx response
    mock_response = MagicMock()
    mock_response.json.return_value = {"rates": {"EUR": 0.95}}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        await service.get_rate("USD", "EUR")

        # Verify custom URL was used
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == f"{custom_url}/latest"
