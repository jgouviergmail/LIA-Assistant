"""Flag-ON wiring guards for telephony P4 (skipped when the feature is off).

Run with ``TELEPHONY_ENABLED=true`` to assert the webhook + calls routes mount
and the return-path import chain (LLM factory + notification dispatcher) resolves.
The LLM-type registry parity guard runs unconditionally.
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY


@pytest.mark.unit
def test_telephony_synthesis_llm_type_registered() -> None:
    """The new LLM type is present in both tables (boot parity assert covers it)."""
    assert "telephony_synthesis" in LLM_TYPES_REGISTRY
    assert "telephony_synthesis" in LLM_DEFAULTS
    assert set(LLM_TYPES_REGISTRY) == set(LLM_DEFAULTS)


@pytest.mark.unit
@pytest.mark.skipif(
    not getattr(settings, "telephony_enabled", False),
    reason="telephony disabled — routes are flag-gated",
)
def test_telephony_routes_mounted() -> None:
    """Webhook + calls endpoints are mounted, and the return path imports cleanly."""
    import src.domains.telephony.return_synthesis  # noqa: F401 — get_llm + dispatcher chain
    from src.api.v1.routes import api_router
    from src.domains.telephony.reapers import (  # noqa: F401
        telephony_retention_reaper,
        telephony_stale_call_reaper,
    )

    paths = {getattr(route, "path", "") for route in api_router.routes}
    assert any(p.endswith("/telephony/webhook") for p in paths)
    assert any(p.endswith("/telephony/calls") for p in paths)
