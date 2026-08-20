"""A tool manifest never outlives the agent it belongs to.

Registering a tool whose agent manifest is absent produces an ORPHAN: the
registry logs ``catalogue_tool_orphan``, and the tool sits in a domain the
analyzer cannot route to — advertised, unreachable, and counted against the
catalogue cap of any request that names its domain.

The trap is easy to fall into: the flag-gated families (telephony, peers)
register their agent conditionally, so any tool added to them must carry the
SAME condition. Caught during this very change — three CRM read tools were
registered unconditionally while two of their agents are flag-gated (the
cross-domain reachability suite is what surfaced it).
"""

from __future__ import annotations

import pytest

from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue_loader import initialize_catalogue

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def catalogue() -> AgentRegistry:
    registry = AgentRegistry()
    initialize_catalogue(registry)
    return registry


class TestNoOrphanTool:
    def test_every_tool_has_its_agent_manifest(self, catalogue: AgentRegistry) -> None:
        """The invariant, stated over the WHOLE catalogue rather than a list."""
        agents = {manifest.name for manifest in catalogue.list_agent_manifests()}
        orphans = sorted(
            f"{tool.name} -> {tool.agent}"
            for tool in catalogue.list_tool_manifests()
            if tool.agent and tool.agent not in agents
        )

        assert not orphans, (
            f"{len(orphans)} tool manifest(s) reference an agent the catalogue does not "
            f"register: {orphans}. Either register the agent, or gate the tool on the "
            "same flag as its agent — an orphan is advertised to the planner and "
            "unreachable by the analyzer."
        )


class TestRegistrationOrder:
    def test_flag_gated_families_register_agent_before_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No transient ``catalogue_tool_orphan`` during initialization.

        The final state was already guarded; the ORDER was not — measured in
        prod 2026-08-20: ``get_calls_tool`` registered by the program
        aggregator BEFORE the loader's telephony block registered
        ``telephony_agent``, one warning per worker on every boot. The
        catalogue must register an agent manifest before any of its tools,
        flags on or off.
        """
        from unittest.mock import MagicMock

        from src.core.config import settings as app_settings
        from src.domains.agents.registry import agent_registry as registry_module

        monkeypatch.setattr(app_settings, "telephony_enabled", True, raising=False)
        monkeypatch.setattr(app_settings, "peers_enabled", True, raising=False)
        mock_logger = MagicMock()
        monkeypatch.setattr(registry_module, "logger", mock_logger)

        registry = AgentRegistry()
        initialize_catalogue(registry)

        orphan_calls = [
            call
            for call in mock_logger.warning.call_args_list
            if (call.args and call.args[0] == "catalogue_tool_orphan")
        ]
        assert not orphan_calls, (
            "Tools registered before their agent during catalogue init: "
            f"{[call.kwargs.get('tool') for call in orphan_calls]}"
        )


class TestFlagGatedFamiliesStayConsistent:
    """The two conditional families must be all-or-nothing."""

    @pytest.mark.parametrize("agent_name", ["telephony_agent", "peer_agent"])
    def test_no_tool_of_a_disabled_family_is_advertised(
        self, catalogue: AgentRegistry, agent_name: str
    ) -> None:
        """With the flags off (the test environment), neither family ships."""
        agents = {manifest.name for manifest in catalogue.list_agent_manifests()}
        if agent_name in agents:
            pytest.skip(f"{agent_name} is enabled in this environment")

        advertised = sorted(
            tool.name for tool in catalogue.list_tool_manifests() if tool.agent == agent_name
        )

        assert not advertised, (
            f"{advertised} are advertised while {agent_name} is not registered — "
            "the tool's flag and its agent's flag disagree."
        )
