"""Safety guard: nothing that MUTATES may be executed proactively.

The initiative node (ADR-062) runs *after* a turn and may execute tools the user
never asked for, to enrich the answer. Its whole contract is "read-only
complementary actions". The gate is ``is_initiative_eligible(manifest)``, which
falls back to ``get_tool_category`` — and that, in turn, falls back to
**inferring the category from the tool NAME** when the manifest does not declare
one.

That inference defaults unknown shapes to ``readonly``, so tools whose name
carries no CRUD verb were silently declared safe for proactive execution:

- ``apply_labels_tool``      → Gmail label mutation
- ``complete_task_tool``     → ``client.complete_task(...)``
- ``control_hue_light_tool`` → ``client.update_light(...)``   (physical device)
- ``control_hue_room_tool``  → ``client.control_room(...)``   (physical device)
- ``activate_hue_scene_tool``→ ``client.activate_scene(...)`` (physical device)

The "defense in depth" check in ``initiative_plan._validate_read_only`` does not
catch them: it re-uses the very same eligible list, so it only verifies the LLM
picked a tool that was already offered to it.

The invariant below ties the two independent safety mechanisms together — the
initiative gate and the mutation classifier that guards the invalid-plan safety
net — so a future miscategorisation fails here instead of turning into a
proactive write.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.domains.agents.orchestration.plan_predicates import tool_is_mutation
from src.domains.agents.registry import agent_registry as registry_module
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import (
    is_initiative_eligible,
    is_read_only_tool,
)
from src.domains.agents.registry.catalogue_loader import initialize_catalogue
from src.domains.agents.tools.tool_registry import ensure_tools_loaded, get_all_tools

pytestmark = pytest.mark.unit

# Tools proven to mutate (verified against their client calls), which the name
# heuristic used to classify "readonly".
PROVEN_MUTATING_TOOLS = [
    "apply_labels_tool",
    "complete_task_tool",
    "control_hue_light_tool",
    "control_hue_room_tool",
    "activate_hue_scene_tool",
    # Skill tools: their domain ("query") has no adjacency today, so the
    # initiative path cannot reach them — but the mutation safety net has NO
    # adjacency filter, so a miscategorisation still costs the HITL reroute.
    "run_skill_script",  # "Execute a Python script from a skill's scripts/"
    "import_user_skill",  # "Import … then registers the skill"
]


@pytest.fixture
def registry() -> Iterator[AgentRegistry]:
    """Catalogue-populated global registry, restored afterwards."""
    previous = registry_module._global_registry
    ensure_tools_loaded()
    populated = AgentRegistry()
    initialize_catalogue(populated)
    registry_module._global_registry = populated
    try:
        yield populated
    finally:
        registry_module._global_registry = previous


# ============================================================================
# The invariant
# ============================================================================


def test_no_initiative_eligible_tool_is_a_mutation(registry: AgentRegistry) -> None:
    """A tool LIA may run proactively must never be a mutation.

    Ties the initiative gate to the mutation classifier used by the
    invalid-plan safety net: the two must never disagree.
    """
    offenders: list[str] = []
    eligible = 0

    for tool_name in sorted(get_all_tools()):
        try:
            manifest = registry.get_tool_manifest(tool_name)
        except Exception:
            continue
        if not is_initiative_eligible(manifest):
            continue
        eligible += 1
        if tool_is_mutation(tool_name):
            offenders.append(tool_name)

    assert eligible > 0, "No initiative-eligible tool found — guard is vacuous"
    assert not offenders, (
        "Tools eligible for PROACTIVE execution that mutate data: "
        f"{offenders}. Declare an explicit non-readonly `tool_category` on "
        "their catalogue manifest."
    )


# ============================================================================
# Regressions on the five proven mutators
# ============================================================================


class TestProvenMutatorsAreNotProactive:
    @pytest.mark.parametrize("tool_name", PROVEN_MUTATING_TOOLS)
    def test_not_initiative_eligible(self, registry: AgentRegistry, tool_name: str) -> None:
        manifest = registry.get_tool_manifest(tool_name)
        assert not is_initiative_eligible(manifest)

    @pytest.mark.parametrize("tool_name", PROVEN_MUTATING_TOOLS)
    def test_not_read_only(self, registry: AgentRegistry, tool_name: str) -> None:
        manifest = registry.get_tool_manifest(tool_name)
        assert not is_read_only_tool(manifest)

    @pytest.mark.parametrize("tool_name", PROVEN_MUTATING_TOOLS)
    def test_visible_to_the_mutation_safety_net(
        self, registry: AgentRegistry, tool_name: str
    ) -> None:
        """``plan_contains_mutation`` must see them, so an unconverged invalid
        plan calling them is rerouted to a HITL clarification."""
        assert tool_is_mutation(tool_name) is True

    @pytest.mark.parametrize("tool_name", PROVEN_MUTATING_TOOLS)
    def test_category_is_declared_explicitly(self, registry: AgentRegistry, tool_name: str) -> None:
        """Never rely on name inference for a mutating tool — declare it."""
        manifest = registry.get_tool_manifest(tool_name)
        assert manifest.tool_category is not None


# ============================================================================
# Read-only siblings must stay proactively usable (no over-correction)
# ============================================================================


class TestReadOnlySiblingsUnaffected:
    @pytest.mark.parametrize(
        "tool_name",
        ["list_hue_lights_tool", "list_hue_rooms_tool", "list_hue_scenes_tool"],
    )
    def test_hue_list_tools_stay_read_only(self, registry: AgentRegistry, tool_name: str) -> None:
        manifest = registry.get_tool_manifest(tool_name)
        assert is_read_only_tool(manifest)
        assert tool_is_mutation(tool_name) is False

    @pytest.mark.parametrize("tool_name", ["get_emails_tool", "get_tasks_tool"])
    def test_search_tools_remain_initiative_eligible(
        self, registry: AgentRegistry, tool_name: str
    ) -> None:
        manifest = registry.get_tool_manifest(tool_name)
        assert is_initiative_eligible(manifest)
