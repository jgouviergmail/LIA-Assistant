"""Diagnostics catalogue registration is gated on DIAGNOSTICS_ENABLED.

Flag off ⇒ the agent and its four tools are ABSENT from the catalogue (the
subsystem must not exist at runtime); flag on ⇒ agent registered before its
tools (orphan-order invariant) with the enforced bounds published.
"""

from __future__ import annotations

import pytest

from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue_loader import initialize_catalogue

pytestmark = pytest.mark.unit

_TOOL_NAMES = {
    "platform_health_tool",
    "platform_metrics_tool",
    "platform_logs_tool",
    "platform_incidents_tool",
}


def _build(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> AgentRegistry:
    from src.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "diagnostics_enabled", enabled, raising=False)
    registry = AgentRegistry()
    initialize_catalogue(registry)
    return registry


class TestFlagGating:
    def test_flag_off_registers_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        registry = _build(monkeypatch, enabled=False)
        agents = {m.name for m in registry.list_agent_manifests()}
        tools = {m.name for m in registry.list_tool_manifests()}
        assert "diagnostics_agent" not in agents
        assert not (_TOOL_NAMES & tools)

    def test_flag_on_registers_agent_and_four_tools(self, monkeypatch: pytest.MonkeyPatch) -> None:
        registry = _build(monkeypatch, enabled=True)
        agents = {m.name for m in registry.list_agent_manifests()}
        tools = {m.name for m in registry.list_tool_manifests()}
        assert "diagnostics_agent" in agents
        assert _TOOL_NAMES <= tools

    def test_enforced_bounds_are_published(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ADR-184: the clamps the builders apply must appear as constraints."""
        from src.core.constants import (
            DIAGNOSTICS_LOKI_MAX_LINES,
            DIAGNOSTICS_LOKI_MAX_RANGE_HOURS,
        )

        registry = _build(monkeypatch, enabled=True)
        logs = next(m for m in registry.list_tool_manifests() if m.name == "platform_logs_tool")
        by_name = {p.name: p for p in logs.parameters}
        limit_max = next(c.value for c in by_name["limit"].constraints if c.kind == "maximum")
        minutes_max = next(c.value for c in by_name["minutes"].constraints if c.kind == "maximum")
        assert limit_max == DIAGNOSTICS_LOKI_MAX_LINES
        assert minutes_max == DIAGNOSTICS_LOKI_MAX_RANGE_HOURS * 60
        services_enum = next(c.value for c in by_name["service"].constraints if c.kind == "enum")
        assert "api" in services_enum
