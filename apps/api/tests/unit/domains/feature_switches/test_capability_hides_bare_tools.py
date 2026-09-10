"""A switched-off capability hides its TOOLS, not only its agents (B7).

Two layers protect a disabled capability: the routes (or a service chokepoint)
REFUSE it, and the planner is never offered its tools. The second layer is not
redundant — a planner that SEES a tool it cannot run plans an invented dead end,
and the person reads a failure where they should have read « I cannot do that ».

`CapabilitySpec.agents` covers a capability that owns an agent. Two do not:
delegation to a sub-agent (ADR-083 removed its REST surface, the tool lives in
the graph) and the ephemeral Python sandbox (ADR-249). Switched off, their tools
stayed in the catalogue and only failed at call time — exactly the shape the
manifest rule of ADR-249 exists to prevent.

`CapabilitySpec.tools` closes it: a capability may name tools directly, and the
planner filter unions the two sources.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.feature_switches.registry import (
    CAPABILITY_SPECS,
    PlatformCapability,
    disabled_tool_names,
)

pytestmark = pytest.mark.unit


class TestACapabilityMayNameItsToolsDirectly:
    def test_delegation_names_the_tool_it_governs(self) -> None:
        spec = CAPABILITY_SPECS[PlatformCapability.SUB_AGENTS]

        assert "delegate_to_sub_agent_tool" in spec.tools

    def test_the_sandbox_names_the_tool_it_governs(self) -> None:
        spec = CAPABILITY_SPECS[PlatformCapability.PYTHON_SANDBOX]

        assert "run_python_tool" in spec.tools

    def test_a_capability_with_an_agent_needs_no_bare_tool(self) -> None:
        # Naming both would be two authorities on the same hiding: the agent's
        # manifests already carry every tool it owns.
        for capability, spec in CAPABILITY_SPECS.items():
            assert not (spec.agents and spec.tools), capability.value


class TestWhatTheFilterHides:
    def test_a_disabled_capability_hides_its_bare_tools(self) -> None:
        hidden = disabled_tool_names({PlatformCapability.PYTHON_SANDBOX})

        assert hidden == {"run_python_tool"}

    def test_several_disabled_capabilities_union_their_tools(self) -> None:
        hidden = disabled_tool_names(
            {PlatformCapability.PYTHON_SANDBOX, PlatformCapability.SUB_AGENTS}
        )

        assert hidden == {"run_python_tool", "delegate_to_sub_agent_tool"}

    def test_a_capability_that_owns_an_agent_hides_nothing_here(self) -> None:
        # Its tools come from the agent walk, which knows every manifest the
        # agent carries — this list is only for the capabilities that own none.
        assert disabled_tool_names({PlatformCapability.TELEPHONY}) == set()

    def test_nothing_disabled_hides_nothing(self) -> None:
        assert disabled_tool_names(set()) == set()


class TestThePlannerFilterUnionsBothSources:
    async def test_it_hides_a_bare_tool_even_with_no_disabled_agent(self) -> None:
        from src.domains.agents.services.planner_capability_filter import (
            tools_hidden_by_capabilities,
        )

        registry = MagicMock()
        registry.list_tool_manifests.return_value = []
        with (
            patch(
                "src.domains.feature_switches.registry.disabled_capabilities",
                new=AsyncMock(return_value={PlatformCapability.PYTHON_SANDBOX}),
            ),
        ):
            hidden = await tools_hidden_by_capabilities(registry)

        # Before this, the early return on « no disabled agent » sent the
        # planner the sandbox tool of a capability an operator had switched off.
        assert hidden == {"run_python_tool"}

    async def test_it_still_hides_the_tools_of_a_disabled_agent(self) -> None:
        from src.domains.agents.services.planner_capability_filter import (
            tools_hidden_by_capabilities,
        )

        manifest = MagicMock()
        manifest.name = "make_call_tool"
        registry = MagicMock()
        registry.list_tool_manifests.return_value = [manifest]
        with (
            patch(
                "src.domains.feature_switches.registry.disabled_capabilities",
                new=AsyncMock(return_value={PlatformCapability.TELEPHONY}),
            ),
        ):
            hidden = await tools_hidden_by_capabilities(registry)

        assert "make_call_tool" in hidden

    async def test_nothing_disabled_still_costs_no_catalogue_walk(self) -> None:
        from src.domains.agents.services.planner_capability_filter import (
            tools_hidden_by_capabilities,
        )

        registry = MagicMock()
        with patch(
            "src.domains.feature_switches.registry.disabled_capabilities",
            new=AsyncMock(return_value=set()),
        ):
            hidden = await tools_hidden_by_capabilities(registry)

        assert hidden == set()
        registry.list_tool_manifests.assert_not_called()
