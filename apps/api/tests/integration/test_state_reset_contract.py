"""Contract: cross-test global caches/singletons are reset between tests.

The full integration suite was order-dependent (12 failures in a full run,
same tests green in isolation): pricing/cost tests read whatever an earlier
test left in the process-wide pricing caches, and the semantic-expansion
tests depend on the semantic singletons being in their canonical boot state.
The autouse fixture ``_reset_shared_pricing_and_semantic_state``
(tests/integration/conftest.py) resets those states around every test; this
file PROVES it: the first test deliberately pollutes every covered state, the
second (same file → guaranteed to run after) asserts pristine state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.infrastructure.cache import pricing_cache as pricing_cache_module
from src.infrastructure.cache.pricing_cache import CachedModelPrice, PricingCacheData
from src.infrastructure.external.currency_api import CurrencyRateService

pytestmark = pytest.mark.integration


def test_1_deliberately_pollute_shared_state() -> None:
    """Pollute every state the reset fixture must cover (the 'attacker')."""
    # Class-attribute rate cache (shared by ALL instances — the exact
    # "singleton holding shared state" trap).
    CurrencyRateService._rate_cache["USD_EUR"] = (Decimal("0.5"), datetime.now(UTC))

    # Module-level pricing snapshot.
    pricing_cache_module._local_cache = PricingCacheData(
        models={
            "polluted-model": CachedModelPrice(
                input_unit_price=1.0,
                output_unit_price=2.0,
                cached_input_unit_price=0.0,
            )
        },
        usd_eur_rate=0.5,
        last_refresh_ts=0.0,
    )

    # Semantic singletons: leave the registry EMPTY (reset without reload) —
    # the worst state for any later test relying on the boot-loaded types.
    from src.domains.agents.semantic.expansion_service import reset_expansion_service
    from src.domains.agents.semantic.type_registry import reset_registry
    from src.domains.agents.services.query_analyzer_service import (
        reset_query_analyzer_service,
    )

    reset_registry()
    reset_expansion_service()
    reset_query_analyzer_service()


def test_2_shared_state_is_pristine_after_polluting_test() -> None:
    """Every polluted state must be back to its canonical boot state."""
    from src.domains.agents.semantic.type_registry import get_registry

    assert CurrencyRateService._rate_cache == {}, (
        "CurrencyRateService._rate_cache (class attribute) leaked from the "
        "previous test — the autouse reset fixture is broken"
    )
    assert pricing_cache_module._local_cache is None, (
        "pricing_cache._local_cache (module-level snapshot) leaked from the " "previous test"
    )
    # Semantic registry must be back to the canonical boot state (core types
    # loaded), not empty and not None.
    registry = get_registry()
    assert "email_address" in registry, (
        "semantic TypeRegistry is not in its canonical boot state (core types "
        "missing) — expansion behavior would depend on test order"
    )
    assert "physical_address" in registry
