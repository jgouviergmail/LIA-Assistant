"""Guard + regression tests for ``tool_is_mutation`` (mutation classification).

Why this matters — ``plan_contains_mutation`` guards a SAFETY NET in
``semantic_validator_node``: when the replanner exhausts its iterations, the
max-iterations bypass would execute a still-INVALID plan. For mutation plans
that is silently destructive (prod incident 2026-07-17: a calendar event created
on the wrong day), so those are rerouted to a HITL clarification instead;
read-only plans keep the bypass. A tool wrongly classified read-only therefore
**executes an invalid mutation plan with no confirmation**.

Classification has two sources:
- an EXPLICITLY declared ``tool_category`` on the catalogue manifest — hand-
  written ground truth;
- otherwise a name-substring heuristic (``MUTATION_TOOL_PATTERNS``).

The explicit declaration must WIN. It used not to: ``cancel_reminder_tool``
(category "delete"), ``edit_image`` and ``generate_image`` (category "create")
were all classified read-only because their names carry none of the nine
hard-coded verbs.

The guard below re-derives the expectation from the registry itself, so any
future tool whose declaration contradicts the heuristic fails here rather than
silently losing the safety net.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.domains.agents.orchestration.plan_predicates import (
    plan_contains_mutation,
    tool_is_mutation,
)
from src.domains.agents.registry import agent_registry as registry_module
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import is_read_only_tool
from src.domains.agents.registry.catalogue_loader import initialize_catalogue
from src.domains.agents.tools.tool_registry import ensure_tools_loaded, get_all_tools

pytestmark = pytest.mark.unit


@pytest.fixture
def populated_registry() -> Iterator[AgentRegistry]:
    """Install a catalogue-populated global registry, then restore the previous one.

    Save/restore (never blank-out): other tests in the same process may rely on
    whatever registry was already installed.
    """
    previous = registry_module._global_registry
    ensure_tools_loaded()
    registry = AgentRegistry()
    initialize_catalogue(registry)
    registry_module._global_registry = registry
    try:
        yield registry
    finally:
        registry_module._global_registry = previous


# ============================================================================
# Systemic guard: an explicit manifest category is authoritative
# ============================================================================


def test_explicit_manifest_category_always_wins_over_name_heuristic(
    populated_registry: AgentRegistry,
) -> None:
    """Every tool that DECLARES a category must be classified accordingly."""
    mismatches: list[str] = []
    checked = 0

    for tool_name in sorted(get_all_tools()):
        try:
            manifest = populated_registry.get_tool_manifest(tool_name)
        except Exception:
            continue  # no catalogue manifest → heuristic-only, covered below
        if manifest.tool_category is None:
            continue  # inferred category is itself a name heuristic, not truth
        checked += 1
        expected = not is_read_only_tool(manifest)
        actual = tool_is_mutation(tool_name)
        if actual != expected:
            mismatches.append(
                f"{tool_name}: declared category={manifest.tool_category!r} "
                f"→ expected mutation={expected}, got {actual}"
            )

    assert checked > 0, "No tool declares an explicit category — guard is vacuous"
    assert not mismatches, "Declared category contradicts classification:\n" + "\n".join(mismatches)


# ============================================================================
# Regressions: the three tools the name heuristic missed
# ============================================================================


class TestExplicitlyDeclaredMutations:
    @pytest.mark.parametrize("tool_name", ["cancel_reminder_tool", "edit_image", "generate_image"])
    def test_declared_mutation_is_classified_as_mutation(
        self, populated_registry: AgentRegistry, tool_name: str
    ) -> None:
        """Their names carry no mutation verb, but their manifests declare
        'delete'/'create' — the safety net must see them."""
        assert tool_is_mutation(tool_name) is True

    def test_plan_with_declared_mutation_is_a_mutation_plan(
        self, populated_registry: AgentRegistry
    ) -> None:
        """End-to-end on the predicate that gates the safety net."""
        plan = {"steps": [{"tool_name": "cancel_reminder_tool"}]}
        assert plan_contains_mutation(plan) is True


# ============================================================================
# Preserved behaviour: the name heuristic remains the fallback
# ============================================================================


class TestNameHeuristicFallback:
    @pytest.mark.parametrize(
        "tool_name",
        ["delete_file_tool", "send_email_tool", "create_event_tool", "update_task_tool"],
    )
    def test_mutation_verbs_still_detected(self, tool_name: str) -> None:
        assert tool_is_mutation(tool_name) is True

    @pytest.mark.parametrize(
        "tool_name", ["get_emails_tool", "search_places_tool", "list_labels_tool"]
    )
    def test_read_tools_stay_read(self, tool_name: str) -> None:
        assert tool_is_mutation(tool_name) is False

    def test_unknown_tool_falls_back_to_heuristic(self) -> None:
        """A name absent from the registry must not raise — it degrades to the
        substring heuristic."""
        assert tool_is_mutation("create_widget_tool") is True
        assert tool_is_mutation("get_widget_tool") is False

    def test_empty_name_is_not_a_mutation(self) -> None:
        assert tool_is_mutation("") is False
