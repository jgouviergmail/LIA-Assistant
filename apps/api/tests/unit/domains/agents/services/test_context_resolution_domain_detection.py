"""Tests for domain detection from agent results in ContextResolutionService (ADR-102).

``_detect_domain_from_agent_results`` inspects a turn's agent results and returns
the domain that turn acted on. Its value is compared, in STRATEGY 3 of the
registry extraction, against ``item.meta.domain`` / ``_derive_domain_from_type``
— both of which are the canonical **result_key** (plural, e.g. ``files``,
``weathers``). The detection table therefore MUST also return result_keys.

It historically returned a mix of legacy/singular tokens (``drive`` for files,
``weather`` for weathers, ``wikipedia``/``perplexity`` for their plural keys),
so the ``item_domain == detected_domain`` comparison silently never matched for
those domains and domain-based ordinal reference resolution was inert for them.
"""

from __future__ import annotations

import pytest

from src.domains.agents.services.context_resolution_service import (
    ContextResolutionService,
)

pytestmark = [pytest.mark.unit]


def _detect(data_key: str) -> str | None:
    """Detect the domain of a turn whose result payload carries ``data_key``."""
    service = ContextResolutionService()
    agent_results = {"5:some_agent": {"data": {data_key: [{"id": "x"}]}}}
    return service._detect_domain_from_agent_results(agent_results, 5, "run")


@pytest.mark.parametrize(
    "data_key,expected_result_key",
    [
        ("files", "files"),  # was "drive"
        ("weather", "weathers"),  # was "weather"
        ("forecasts", "weathers"),  # was "weather"
        ("articles", "wikipedias"),  # was "wikipedia"
        ("results", "perplexitys"),  # was "perplexity"
        # Already-correct entries (regression guard):
        ("emails", "emails"),
        ("contacts", "contacts"),
        ("events", "events"),
        ("tasks", "tasks"),
        ("places", "places"),
    ],
)
def test_detected_domain_is_canonical_result_key(data_key: str, expected_result_key: str) -> None:
    """Every detected domain must be the canonical result_key of the payload.

    Otherwise ``item_domain == detected_domain`` in STRATEGY 3 never matches and
    domain-based reference resolution silently degrades.
    """
    assert _detect(data_key) == expected_result_key
