"""The Google Maps Platform counter fails CLOSED when nobody is accounting.

``track_google_api_call`` records into the ambient ``TrackingContext``. Without
one it used to « do nothing » — by design, said its docstring — which turned
every paid call made outside a turn (the heartbeat's departure advice, the
briefing's weather, a meeting's reverse geocoding, the static-map proxies)
into a euro the deployment paid and nobody filed: measured 2026-09-19 on
dev, 3 020 rows in ``google_api_usage_logs``, not one outside a chat turn.

An unaccounted call is now counted and named, so a surface that reaches a
paid client with no tracker shows up on the dashboard rather than in the
provider's invoice.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

from src.core.context import current_tracker
from src.domains.chat.service import TrackingContext
from src.domains.connectors.clients.google_api_tracker import track_google_api_call
from src.infrastructure.observability.metrics_usage_limits import (
    google_api_calls_unaccounted_total,
)

pytestmark = pytest.mark.unit


def _unaccounted(api_name: str) -> float:
    return google_api_calls_unaccounted_total.labels(api_name=api_name)._value.get()


@pytest.fixture
def _no_tracker() -> None:
    token = current_tracker.set(None)
    yield
    current_tracker.reset(token)


@pytest.mark.usefixtures("_no_tracker")
def test_a_call_with_no_tracker_is_counted_and_named() -> None:
    before = _unaccounted("routes")
    with patch("src.domains.connectors.clients.google_api_tracker.logger") as log:
        track_google_api_call("routes", "/directions/v2:computeRoutes", cached=False)
    assert _unaccounted("routes") == before + 1
    log.warning.assert_called_once()
    assert log.warning.call_args.args[0] == "google_api_call_unaccounted"
    assert log.warning.call_args.kwargs["api_name"] == "routes"


@pytest.mark.usefixtures("_no_tracker")
def test_a_cache_hit_with_no_tracker_costs_nothing_and_is_not_counted() -> None:
    before = _unaccounted("places")
    with patch("src.domains.connectors.clients.google_api_tracker.logger") as log:
        track_google_api_call("places", "/places:searchText", cached=True)
    assert _unaccounted("places") == before
    log.warning.assert_not_called()


async def test_a_call_under_a_tracker_is_filed_and_not_counted() -> None:
    before = _unaccounted("places")
    tracker = TrackingContext("run", uuid.uuid4(), "session", None)
    with patch(
        "src.domains.google_api.pricing_service.GoogleApiPricingService.get_cost_per_request",
        return_value=(Decimal("0.032"), Decimal("0.029"), Decimal("0.91")),
    ):
        async with tracker:
            track_google_api_call("places", "/places:searchText", cached=False)
            assert tracker.pending_families()["google_api"] == 1
            tracker._google_api_records.clear()  # nothing to persist at exit
    assert _unaccounted("places") == before


async def test_a_billed_batch_is_filed_as_its_units() -> None:
    """Google bills a Route Matrix per element: six elements are six billable events."""
    tracker = TrackingContext("run", uuid.uuid4(), "session", None)
    with patch(
        "src.domains.google_api.pricing_service.GoogleApiPricingService.get_cost_per_request",
        return_value=(Decimal("0.010"), Decimal("0.009"), Decimal("0.9")),
    ):
        async with tracker:
            track_google_api_call(
                "routes", "/distanceMatrix/v2:computeRouteMatrix:pro", cached=False, units=6
            )
            [record] = tracker._google_api_records
            assert record.units == 6
            assert (record.cost_usd, record.cost_eur) == (Decimal("0.060"), Decimal("0.054"))
            assert tracker.get_summary()["google_api_requests"] == 6
            tracker._google_api_records.clear()  # nothing to persist at exit
