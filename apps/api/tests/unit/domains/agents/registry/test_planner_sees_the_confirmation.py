"""What the planner is told about confirmation must be TRUE (ADR-263).

``export_for_prompt`` published ``requires_approval = permissions.hitl_required``,
which is ``False`` for the 24 tools that build a draft — and a draft is exactly
the case where the user WILL be asked. So the catalogue told the planner "no
confirmation needed" about every email, event, contact and task the assistant
can write.

That is ADR-184's rule pointing at itself: *what a system enforces, it must
publish to whoever produces the value.* The confirmation is enforced by the
declared ``mutation_policy``, so that is what the planner must read.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.registry.catalogue import requires_user_approval

pytestmark = [pytest.mark.unit]


class _Permissions:
    def __init__(self, hitl_required: bool) -> None:
        self.hitl_required = hitl_required


class _Manifest:
    def __init__(self, policy: str | None, hitl_required: bool = False) -> None:
        self.mutation_policy = policy
        self.permissions = _Permissions(hitl_required)


class TestTheAnswerFollowsThePolicy:
    @pytest.mark.parametrize("policy", ["draft", "confirm"])
    def test_a_tool_the_user_will_be_asked_about_says_so(self, policy: str) -> None:
        assert requires_user_approval(_Manifest(policy)) is True

    @pytest.mark.parametrize("policy", ["read", "reversible", "artefact", "sandboxed"])
    def test_a_tool_that_acts_without_asking_says_so(self, policy: str) -> None:
        """No paranoia: Hue, the browser and image generation do not ask."""
        assert requires_user_approval(_Manifest(policy)) is False

    def test_an_explicit_hitl_requirement_still_wins(self) -> None:
        """An operator's ``hitl_required`` (MCP_HITL_REQUIRED) is not overridden."""
        assert requires_user_approval(_Manifest("reversible", hitl_required=True)) is True

    def test_an_undeclared_tool_falls_back_to_the_permission(self) -> None:
        """A third-party manifest may carry no policy; its permission still reads."""
        assert requires_user_approval(_Manifest(None, hitl_required=True)) is True
        assert requires_user_approval(_Manifest(None, hitl_required=False)) is False

    def test_a_manifest_without_permissions_does_not_explode(self) -> None:
        """The catalogue export must never be the thing that breaks a turn."""

        class _Bare:
            mutation_policy = "read"

        assert requires_user_approval(_Bare()) is False


@pytest.fixture
def catalogue() -> Any:
    """A real catalogue installed globally, and REMOVED afterwards.

    Leaving a registry behind is how a test file becomes another file's flake:
    the global is shared by every test in the same xdist worker.
    """
    from src.domains.agents.registry import reset_global_registry, set_global_registry
    from src.domains.agents.registry.agent_registry import AgentRegistry
    from src.domains.agents.registry.catalogue_loader import initialize_catalogue

    registry = AgentRegistry()
    initialize_catalogue(registry)
    set_global_registry(registry)
    try:
        yield registry
    finally:
        reset_global_registry()


class TestTheCatalogueActuallyPublishesIt:
    def test_a_draft_tool_is_exported_as_requiring_approval(self, catalogue: Any) -> None:
        """The measured defect, on the real catalogue: send_email_tool."""
        registry = catalogue

        manifest = registry.get_tool_manifest("send_email_tool")
        assert manifest.mutation_policy == "draft"
        assert manifest.permissions.hitl_required is False, (
            "precondition: this tool's permission says no approval — which is "
            "why reading the permission alone was the defect"
        )
        assert requires_user_approval(manifest) is True

        exported = registry.export_for_prompt()
        entries = [
            tool
            for agent in exported.get("agents", [])
            for tool in agent.get("tools", [])
            if tool.get("name") == "send_email_tool"
        ]
        assert entries, "send_email_tool is missing from the planner catalogue"
        assert all(entry["requires_approval"] is True for entry in entries)
