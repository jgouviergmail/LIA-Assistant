"""FOR_EACH bulk-operation gate: mutations must never slip into the lenient regime.

``detect_for_each_scope`` decides whether a FOR_EACH step ("reply to each of
these emails") needs a HITL confirmation before running N times. Two regimes:

- mutation      → approval required from ``for_each_mutation_threshold`` (1)
- non-mutation  → approval only from ``for_each_warning_threshold`` (10)

So a mutation misclassified as read-only executes **up to 9 times with no
confirmation at all**.

Both production call sites (``task_orchestrator_node`` and
``parallel_executor``) pass ``is_mutation=False`` with the comment
"Auto-detected from tool_name", so the auto-detection is ALWAYS the deciding
oracle — it is never bypassed.

That auto-detection used a private substring set that had drifted from the
canonical ``MUTATION_TOOL_PATTERNS``: it was missing ``reply`` and ``forward``,
so ``reply_email_tool`` / ``forward_email_tool`` were treated as read-only. It
also could not see the manifest-declared categories fixed elsewhere
(``apply_labels_tool``, ``complete_task_tool``, ``cancel_reminder_tool`` …).

The invariant below binds this gate to the single mutation oracle
(``tool_is_mutation``), so the two can never drift again.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.core.config import settings
from src.domains.agents.orchestration.plan_predicates import tool_is_mutation
from src.domains.agents.registry import agent_registry as registry_module
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue_loader import initialize_catalogue
from src.domains.agents.services.hitl.scope_detector import detect_for_each_scope
from src.domains.agents.tools.tool_registry import ensure_tools_loaded, get_all_tools

pytestmark = pytest.mark.unit


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


def _scope_at(count: int, tool_name: str):
    """Mirror the production call sites: is_mutation is always auto-detected."""
    return detect_for_each_scope(
        iteration_count=count,
        tool_name=tool_name,
        is_mutation=False,
        for_each_max=count,
    )


# ============================================================================
# The invariant
# ============================================================================


def test_for_each_gate_agrees_with_the_mutation_oracle(registry: AgentRegistry) -> None:
    """At the mutation threshold, approval is required IFF the tool mutates.

    Thresholds are read from settings (never hard-coded): at
    ``for_each_mutation_threshold`` a mutation always needs approval, while a
    read-only tool does not until ``for_each_warning_threshold``.
    """
    mutation_threshold = settings.for_each_mutation_threshold
    warning_threshold = settings.for_each_warning_threshold
    assert (
        mutation_threshold < warning_threshold
    ), "Thresholds no longer separate the two regimes — this guard would be vacuous"

    offenders: list[str] = []
    for tool_name in sorted(get_all_tools()):
        expected = tool_is_mutation(tool_name)
        actual = _scope_at(mutation_threshold, tool_name).requires_approval
        if actual != expected:
            offenders.append(f"{tool_name}: mutation={expected}, requires_approval={actual}")

    assert not offenders, (
        "FOR_EACH gate disagrees with the mutation oracle — these run in bulk "
        "without confirmation:\n" + "\n".join(offenders)
    )


# ============================================================================
# Regressions: mutations the private substring set could not see
# ============================================================================


class TestMutationsRequireConfirmation:
    @pytest.mark.parametrize(
        "tool_name",
        [
            "reply_email_tool",  # missing from the old substring set
            "forward_email_tool",  # missing from the old substring set
            "apply_labels_tool",  # declared "update" on its manifest
            "complete_task_tool",  # declared "update" on its manifest
            "cancel_reminder_tool",  # declared "delete" on its manifest
            "run_skill_script",  # declared "update" — executes a script
        ],
    )
    def test_bulk_mutation_requires_approval_below_the_readonly_threshold(
        self, registry: AgentRegistry, tool_name: str
    ) -> None:
        """A handful of iterations — far under the read-only warning threshold —
        must still be gated because the operation mutates."""
        count = settings.for_each_warning_threshold - 1
        assert count >= settings.for_each_mutation_threshold

        scope = _scope_at(count, tool_name)

        assert (
            scope.requires_approval is True
        ), f"{tool_name} would run {count} times with no confirmation"

    @pytest.mark.parametrize("tool_name", ["send_email_tool", "delete_email_tool"])
    def test_already_detected_mutations_still_gated(
        self, registry: AgentRegistry, tool_name: str
    ) -> None:
        """No regression on the verbs the old set did cover."""
        assert _scope_at(settings.for_each_mutation_threshold, tool_name).requires_approval is True


# ============================================================================
# No over-correction: read-only bulk keeps the lenient regime
# ============================================================================


class TestReadOnlyKeepsLenientRegime:
    @pytest.mark.parametrize(
        "tool_name", ["get_emails_tool", "search_places_tool", "get_current_weather_tool"]
    )
    def test_small_read_only_batch_needs_no_confirmation(
        self, registry: AgentRegistry, tool_name: str
    ) -> None:
        """Asking for confirmation on a harmless read would only annoy."""
        count = settings.for_each_approval_threshold - 1
        assert not _scope_at(count, tool_name).requires_approval

    @pytest.mark.parametrize("tool_name", ["get_emails_tool", "search_places_tool"])
    def test_large_read_only_batch_still_warns(
        self, registry: AgentRegistry, tool_name: str
    ) -> None:
        """Volume alone remains a reason to confirm."""
        assert _scope_at(settings.for_each_warning_threshold, tool_name).requires_approval

    def test_explicit_is_mutation_flag_still_honoured(self, registry: AgentRegistry) -> None:
        """A caller that already knows must not be overridden by detection."""
        scope = detect_for_each_scope(
            iteration_count=settings.for_each_mutation_threshold,
            tool_name="get_emails_tool",
            is_mutation=True,
            for_each_max=1,
        )
        assert scope.requires_approval is True
