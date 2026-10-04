"""Unit tests for GoogleApiPricingService: what one Maps Platform request costs."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest
from structlog.testing import capture_logs

from src.domains.google_api import pricing_service
from src.domains.google_api.pricing_service import GoogleApiPricingService
from tests.support.structlog_capture import fresh_module_logger

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_module_logger() -> Iterator[None]:
    """Keep `capture_logs` reliable under xdist — see `tests/support`."""
    yield from fresh_module_logger(pricing_service)


@pytest.fixture(autouse=True)
def _prices() -> Iterator[None]:
    saved = (GoogleApiPricingService._pricing_cache, GoogleApiPricingService._usd_eur_rate)
    GoogleApiPricingService._pricing_cache = {
        "places:/places:searchText": Decimal("32.0000"),
        "street_view:/streetview/metadata": Decimal("0.0000"),
    }
    GoogleApiPricingService._usd_eur_rate = Decimal("0.85")
    yield
    GoogleApiPricingService._pricing_cache, GoogleApiPricingService._usd_eur_rate = saved


def _missing_price_warnings(logs: list[dict]) -> list[dict]:
    return [entry for entry in logs if entry["event"] == "google_api_pricing_not_found"]


def test_a_priced_request_costs_its_thousandth_at_the_cached_rate() -> None:
    usd, eur, rate = GoogleApiPricingService.get_cost_per_request("places", "/places:searchText")

    assert (usd, eur, rate) == (Decimal("0.032"), Decimal("0.0272"), Decimal("0.85"))


def test_a_free_request_costs_nothing_and_is_not_reported_missing() -> None:
    # The seed declares Street View metadata free (0.0000): measured 2026-10-03,
    # every metadata lookup logged « pricing not found » for a SKU it had found.
    with capture_logs() as logs:
        usd, eur, _ = GoogleApiPricingService.get_cost_per_request(
            "street_view", "/streetview/metadata"
        )

    assert (usd, eur) == (Decimal("0"), Decimal("0"))
    assert _missing_price_warnings(logs) == []


def test_an_undeclared_request_costs_nothing_and_says_so() -> None:
    with capture_logs() as logs:
        usd, eur, _ = GoogleApiPricingService.get_cost_per_request("routes", "/unknown")

    assert (usd, eur) == (Decimal("0"), Decimal("0"))
    warnings = _missing_price_warnings(logs)
    assert [(w["api_name"], w["endpoint"]) for w in warnings] == [("routes", "/unknown")]
