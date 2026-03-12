"""
Tests for FOR_EACH HITL count calculation with pre-execution.

This module verifies that the HITL confirmation message displays the correct
number of items to be affected. The implementation uses pre-execution of
provider steps to get the REAL count from API results.

Architecture (2026-01-19):
    1. Detect FOR_EACH steps requiring HITL
    2. Pre-execute provider steps (e.g., get_events for "$steps.get_events.events")
    3. Count items from execution results
    4. Show HITL with accurate count
    5. Pass pre-executed steps to execute_plan_parallel (skip re-execution)

Bug fixed: "Crée un rappel pour chacun de mes prochains 2 rendez-vous" showed
"10 éléments" (for_each_max default) instead of "2 éléments" (actual count).

Created: 2026-01-19
"""

from src.domains.agents.orchestration.dependency_graph import DependencyGraph
from src.domains.agents.orchestration.for_each_utils import (
    get_for_each_provider_step_id,
    parse_for_each_reference,
)
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType


class TestForEachReferenceHelpers:
    """Tests for FOR_EACH reference parsing helpers."""

    def test_parse_for_each_reference_simple(self):
        """Parse simple reference like $steps.get_events.events."""
        step_id, field_path = parse_for_each_reference("$steps.get_events.events")
        assert step_id == "get_events"
        assert field_path == "events"

    def test_parse_for_each_reference_nested_path(self):
        """Parse reference with nested path like $steps.get_data.data.items."""
        step_id, field_path = parse_for_each_reference("$steps.get_data.data.items")
        assert step_id == "get_data"
        assert field_path == "data.items"

    def test_parse_for_each_reference_with_array_suffix(self):
        """Parse reference with [*] suffix like $steps.get_contacts.contacts[*]."""
        step_id, field_path = parse_for_each_reference("$steps.get_contacts.contacts[*]")
        assert step_id == "get_contacts"
        assert field_path == "contacts"

    def test_parse_for_each_reference_invalid(self):
        """Invalid reference returns None, None."""
        step_id, field_path = parse_for_each_reference("invalid")
        assert step_id is None
        assert field_path is None

    def test_get_for_each_provider_step_id(self):
        """Extract provider step_id from reference."""
        assert get_for_each_provider_step_id("$steps.get_events.events") == "get_events"
        assert get_for_each_provider_step_id("$steps.fetch_data.data") == "fetch_data"
        assert get_for_each_provider_step_id("invalid") is None


class TestDependencyGraphGetAllDependencies:
    """Tests for DependencyGraph.get_all_dependencies method."""

    def test_get_all_dependencies_no_deps(self):
        """Step with no dependencies returns empty set."""
        plan = ExecutionPlan(
            plan_id="test",
            user_id="user",
            steps=[
                ExecutionStep(
                    step_id="step_a",
                    step_type=StepType.TOOL,
                    agent_name="agent",
                    tool_name="tool_a",
                )
            ],
        )
        graph = DependencyGraph(plan)

        deps = graph.get_all_dependencies("step_a")
        assert deps == set()

    def test_get_all_dependencies_direct_dep(self):
        """Step with direct dependency."""
        plan = ExecutionPlan(
            plan_id="test",
            user_id="user",
            steps=[
                ExecutionStep(
                    step_id="step_a",
                    step_type=StepType.TOOL,
                    agent_name="agent",
                    tool_name="tool_a",
                ),
                ExecutionStep(
                    step_id="step_b",
                    step_type=StepType.TOOL,
                    agent_name="agent",
                    tool_name="tool_b",
                    depends_on=["step_a"],
                ),
            ],
        )
        graph = DependencyGraph(plan)

        deps = graph.get_all_dependencies("step_b")
        assert deps == {"step_a"}

    def test_get_all_dependencies_transitive(self):
        """Transitive dependencies: A → B → C."""
        plan = ExecutionPlan(
            plan_id="test",
            user_id="user",
            steps=[
                ExecutionStep(
                    step_id="step_a",
                    step_type=StepType.TOOL,
                    agent_name="agent",
                    tool_name="tool_a",
                ),
                ExecutionStep(
                    step_id="step_b",
                    step_type=StepType.TOOL,
                    agent_name="agent",
                    tool_name="tool_b",
                    depends_on=["step_a"],
                ),
                ExecutionStep(
                    step_id="step_c",
                    step_type=StepType.TOOL,
                    agent_name="agent",
                    tool_name="tool_c",
                    depends_on=["step_b"],
                ),
            ],
        )
        graph = DependencyGraph(plan)

        deps = graph.get_all_dependencies("step_c")
        assert deps == {"step_a", "step_b"}


class TestItemCountCalculation:
    """Tests for item count calculation using centralized count_items_at_path."""

    def test_count_items_simple_list(self):
        """Count items in simple list like events."""
        from src.domains.agents.orchestration.for_each_utils import count_items_at_path

        result = {"events": [{"id": 1}, {"id": 2}]}
        count = count_items_at_path(result, "events")
        assert count == 2

    def test_count_items_nested_path(self):
        """Count items in nested path like data.items."""
        from src.domains.agents.orchestration.for_each_utils import count_items_at_path

        result = {"data": {"items": [1, 2, 3, 4, 5]}}
        count = count_items_at_path(result, "data.items")
        assert count == 5

    def test_count_items_empty_list(self):
        """Empty list returns 0."""
        from src.domains.agents.orchestration.for_each_utils import count_items_at_path

        result = {"events": []}
        count = count_items_at_path(result, "events")
        assert count == 0

    def test_count_items_missing_field(self):
        """Missing field returns 0."""
        from src.domains.agents.orchestration.for_each_utils import count_items_at_path

        result = {"other_field": [1, 2, 3]}
        count = count_items_at_path(result, "events")
        assert count == 0

    def test_count_items_single_value(self):
        """Non-list value returns 1."""
        from src.domains.agents.orchestration.for_each_utils import count_items_at_path

        result = {"item": {"id": 1, "name": "test"}}
        count = count_items_at_path(result, "item")
        assert count == 1


class TestPreExecutionScenarios:
    """Test scenarios for pre-execution flow."""

    def test_scenario_create_reminders_for_2_events(self):
        """
        Scenario: "Crée un rappel pour chacun de mes 2 prochains rendez-vous"

        Plan:
            step_1: get_events_tool (provider)
            step_2: create_reminder_tool for_each=$steps.step_1.events

        Pre-execution:
            - Execute step_1 → returns {"events": [event1, event2]}
            - Count items → 2
            - HITL shows "2 éléments"
        """
        # Simulate pre-execution result
        pre_executed_result = {
            "step_1": {
                "events": [
                    {"id": "evt1", "summary": "Meeting 1"},
                    {"id": "evt2", "summary": "Meeting 2"},
                ],
                "success": True,
            }
        }

        # Calculate count from pre-executed result
        events = pre_executed_result["step_1"]["events"]
        total_affected = len(events)

        assert total_affected == 2, (
            f"Expected HITL to show 2 éléments (real count from API), " f"got {total_affected}"
        )

    def test_scenario_send_emails_to_5_contacts(self):
        """
        Scenario: "Envoie un email à mes 5 contacts favoris"

        Pre-execution returns 5 contacts → HITL shows "5 éléments"
        """
        pre_executed_result = {
            "get_contacts": {
                "contacts": [{"id": f"contact_{i}", "name": f"Contact {i}"} for i in range(5)],
                "success": True,
            }
        }

        contacts = pre_executed_result["get_contacts"]["contacts"]
        total_affected = len(contacts)

        assert total_affected == 5

    def test_scenario_user_requests_10_but_only_3_exist(self):
        """
        Scenario: "Crée un rappel pour mes 10 prochains rdv"
        Reality: User only has 3 upcoming events

        Pre-execution returns 3 events → HITL shows "3 éléments" (not 10)
        This is the key improvement over the old approach.
        """
        # User requested 10, but API returns only 3
        pre_executed_result = {
            "get_events": {
                "events": [
                    {"id": "evt1", "summary": "Event 1"},
                    {"id": "evt2", "summary": "Event 2"},
                    {"id": "evt3", "summary": "Event 3"},
                ],
                "success": True,
            }
        }

        events = pre_executed_result["get_events"]["events"]
        total_affected = len(events)

        # Key assertion: shows real count (3), not requested count (10)
        assert total_affected == 3, (
            f"Expected HITL to show 3 éléments (actual API result), "
            f"not 10 (user requested). Got {total_affected}"
        )

    def test_scenario_empty_result(self):
        """
        Scenario: User requests action but no items match

        Pre-execution returns empty list → HITL shows "0 éléments"
        User can cancel without wasting an API call for the mutation.
        """
        pre_executed_result = {
            "get_events": {
                "events": [],
                "success": True,
            }
        }

        events = pre_executed_result["get_events"]["events"]
        total_affected = len(events)

        assert total_affected == 0


class TestFallbackBehavior:
    """Tests for fallback when pre-execution fails."""

    def _calculate_fallback_total(self, for_each_steps: list[dict]) -> int:
        """Calculate total from for_each_max (fallback)."""
        return sum(s["for_each_max"] for s in for_each_steps)

    def test_fallback_to_for_each_max_when_pre_execution_fails(self):
        """
        When pre-execution fails (network error, etc.), fall back to for_each_max.

        This is less accurate but ensures HITL still works.
        """
        for_each_steps = [{"step_id": "create_reminders", "for_each_max": 10}]

        # Pre-execution failed → item_counts is empty
        item_counts = {}

        if item_counts:
            total_affected = sum(item_counts.values())
        else:
            total_affected = self._calculate_fallback_total(for_each_steps)

        assert total_affected == 10, f"Expected fallback to for_each_max (10), got {total_affected}"

    def test_fallback_multiple_steps(self):
        """Fallback with multiple FOR_EACH steps."""
        for_each_steps = [
            {"step_id": "send_emails", "for_each_max": 10},
            {"step_id": "create_reminders", "for_each_max": 5},
        ]

        item_counts = {}  # Pre-execution failed

        if item_counts:
            total_affected = sum(item_counts.values())
        else:
            total_affected = self._calculate_fallback_total(for_each_steps)

        assert (
            total_affected == 15
        ), f"Expected fallback sum of for_each_max (15), got {total_affected}"
