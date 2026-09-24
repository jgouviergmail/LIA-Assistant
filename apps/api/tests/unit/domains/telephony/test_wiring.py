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
        telephony_notification_reaper,
        telephony_retention_reaper,
        telephony_stale_call_reaper,
    )

    paths = {getattr(route, "path", "") for route in api_router.routes}
    assert any(p.endswith("/telephony/webhook") for p in paths)
    assert any(p.endswith("/telephony/calls") for p in paths)
    # The live tool call-back (lot 7) mounts with the feature, and hides itself
    # behind its own flag at request time.
    assert any(p.endswith("/telephony/tools/{tool_name}") for p in paths)


def test_notification_reaper_is_wired_into_the_scheduler() -> None:
    """The T1 return-notification reaper must be registered when telephony is enabled
    (a durable outbox with no drain worker would silently never recover).

    The registration lives in ``scheduler_telephony`` since ADR-304 (the startup
    step is frozen at its size cap): the registrar is exercised, and the step is
    held to calling it."""
    import inspect
    from unittest.mock import MagicMock

    from src.core.constants import SCHEDULER_JOB_TELEPHONY_NOTIFICATION_REAPER
    from src.infrastructure.startup import schedulers
    from src.infrastructure.startup.scheduler_telephony import register_telephony_jobs

    scheduler = MagicMock()
    register_telephony_jobs(scheduler)
    registered = {call.kwargs["id"] for call in scheduler.add_job.call_args_list}
    assert SCHEDULER_JOB_TELEPHONY_NOTIFICATION_REAPER in registered
    assert "register_telephony_jobs(scheduler)" in inspect.getsource(schedulers)
