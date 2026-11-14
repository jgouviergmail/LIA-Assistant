"""Wiring guards for telephony P4.

The routes are flag-gated and the flag is off by default, so the route guard
switches it on for one reload of the routes module, then reloads the module
back. It used to skip unless ``TELEPHONY_ENABLED=true``, which is not the
default: it never ran in CI (audit AC-033). The LLM-type registry parity guard
and the scheduler wiring guard run unconditionally.
"""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

from src.core.config import settings
from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY
from tests._routes import capabilities_closing, served_routes


@pytest.mark.unit
def test_telephony_synthesis_llm_type_registered() -> None:
    """The new LLM type is present in both tables (boot parity assert covers it)."""
    assert "telephony_synthesis" in LLM_TYPES_REGISTRY
    assert "telephony_synthesis" in LLM_DEFAULTS
    assert set(LLM_TYPES_REGISTRY) == set(LLM_DEFAULTS)


def _paths_with_telephony(enabled: bool) -> set[str]:
    from src.api.v1 import routes as routes_module

    try:
        with patch.object(settings, "telephony_enabled", enabled):
            router = importlib.reload(routes_module).api_router
            return {route.path for route in served_routes(router) if route.path}
    finally:
        importlib.reload(routes_module)


@pytest.mark.unit
def test_telephony_routes_mounted() -> None:
    """Webhook + calls endpoints are mounted, and the return path imports cleanly."""
    # The return path's import chain (LLM factory + notification dispatcher).
    importlib.import_module("src.domains.telephony.return_synthesis")
    reapers = importlib.import_module("src.domains.telephony.reapers")
    for reaper in ("telephony_notification_reaper", "telephony_retention_reaper"):
        assert callable(getattr(reapers, reaper))
    assert callable(reapers.telephony_stale_call_reaper)

    paths = _paths_with_telephony(enabled=True)

    assert any(p.endswith("/telephony/webhook") for p in paths)
    assert any(p.endswith("/telephony/calls") for p in paths)
    # The live tool call-back (lot 7) mounts with the feature, and hides itself
    # behind its own flag at request time.
    assert any(p.endswith("/telephony/tools/{tool_name}") for p in paths)


@pytest.mark.unit
def test_the_telephony_routes_stay_unmounted_when_the_flag_is_off() -> None:
    """The flag still gates the mount: the guard above is not vacuous."""
    paths = _paths_with_telephony(enabled=False)

    assert not any(p.endswith("/telephony/webhook") for p in paths)


def _telephony_guards(enabled: bool) -> dict[str, frozenset[str]]:
    """``METHOD path`` → the capability guards of every served telephony operation."""
    from src.api.v1 import routes as routes_module

    try:
        with patch.object(settings, "telephony_enabled", enabled):
            router = importlib.reload(routes_module).api_router
            return {
                f"{method} {route.path}": capabilities_closing(route)
                for route in served_routes(router)
                if route.path.startswith("/telephony/")
                for method in route.methods or ()
            }
    finally:
        importlib.reload(routes_module)


@pytest.mark.unit
def test_the_key_removal_is_served_under_the_flag_and_outside_the_switch() -> None:
    """A stored key is the person's record (ADR-280): the operator's switch
    closes calling, the wizard, the history and the identity — never the way
    to take one's own key back. Read on the SERVED operations, where a guard
    declared on any including router would show."""
    served = _telephony_guards(enabled=True)

    records = {
        "DELETE /telephony/connector",
        "GET /telephony/calls",
        "GET /telephony/calls/{call_id}",
        "GET /telephony/identity",
        "DELETE /telephony/identity/number",
        "POST /telephony/webhook",
    }
    assert {operation for operation, guards in served.items() if not guards} == records
    others = {operation: guards for operation, guards in served.items() if operation not in records}
    # The walk read the router: it did not pass on an empty table.
    assert len(others) >= 8
    assert {operation for operation, guards in others.items() if "telephony" not in guards} == set()


@pytest.mark.unit
def test_the_key_removal_stays_unmounted_when_the_flag_is_off() -> None:
    """The deployment flag still mounts the whole surface, this door included."""
    assert _telephony_guards(enabled=False) == {}


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
