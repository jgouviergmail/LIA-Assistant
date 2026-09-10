"""A capability that names a TOOL must name one that exists (cold review).

`assert_capability_agents_exist` refuses to boot when a capability names an
agent that is not registered — a switch whose agents are misspelled would
filter nothing while looking like it works (ADR-085 doctrine).

`CapabilitySpec.tools` was added for the two capabilities that own no agent
(delegation and the ephemeral sandbox) and shipped with NO equivalent guard: a
typo in `"run_python_tool"` would hide nothing, the planner would keep offering
a tool an operator had switched off, and the only symptom would be a plan that
dies at call time. That is exactly the failure the agent assert exists to close,
one field to its right.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.domains.feature_switches.registry import (
    CAPABILITY_SPECS,
    PlatformCapability,
    assert_capability_tools_exist,
)

pytestmark = pytest.mark.unit


def _registry(tool_names: list[str]) -> MagicMock:
    """A registry whose catalogue holds exactly these tools.

    `SimpleNamespace`, never `MagicMock(name=...)`: `name` is reserved by the
    mock constructor to name the MOCK, so the manifest would answer a repr
    instead of its tool name and the guard would look broken.
    """
    registry = MagicMock()
    registry.list_tool_manifests.return_value = [SimpleNamespace(name=name) for name in tool_names]
    return registry


def _declared_tools() -> set[str]:
    return {tool for spec in CAPABILITY_SPECS.values() for tool in spec.tools}


class TestTheGuardRefusesAnUnknownTool:
    def test_a_misspelled_tool_stops_the_boot(self) -> None:
        registry = _registry(["something_else_tool"])

        with pytest.raises(AssertionError, match="run_python_tool|delegate_to_sub_agent_tool"):
            assert_capability_tools_exist(registry)

    def test_it_names_every_offender_rather_than_the_first(self) -> None:
        # An operator fixing one typo must not have to boot again to find the
        # next: the message carries the whole list.
        registry = _registry([])

        with pytest.raises(AssertionError) as raised:
            assert_capability_tools_exist(registry)

        for tool in _declared_tools():
            assert tool in str(raised.value)

    def test_it_passes_when_every_declared_tool_is_registered(self) -> None:
        assert_capability_tools_exist(_registry(sorted(_declared_tools())))


class TestItSkipsWhatTheDeploymentForbids:
    def test_a_capability_the_deployment_disabled_is_not_demanded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Its manifests are legitimately absent — demanding them would fail the
        # boot on a perfectly valid configuration, exactly as the agent guard
        # already reasons.
        from src.core.config import settings

        spec = CAPABILITY_SPECS[PlatformCapability.PYTHON_SANDBOX]
        monkeypatch.setattr(settings, spec.env_flag, False, raising=False)
        remaining = _declared_tools() - set(spec.tools)

        assert_capability_tools_exist(_registry(sorted(remaining)))


class TestTheDeclarationItselfIsSound:
    def test_only_capabilities_without_an_agent_declare_tools(self) -> None:
        # An agent's manifests already carry every tool it owns; naming both
        # would be two authorities on one hiding.
        for capability, spec in CAPABILITY_SPECS.items():
            assert not (spec.agents and spec.tools), capability.value

    def test_every_declared_tool_is_named_once_across_the_registry(self) -> None:
        # Two capabilities hiding the same tool would make « why is it gone? »
        # a question with two answers.
        declared = [tool for spec in CAPABILITY_SPECS.values() for tool in spec.tools]

        assert len(declared) == len(set(declared)), declared
