"""
Tests pour DependencyGraph - Analyse des dépendances et calcul des waves.

Ce module teste:
1. Le chaînage implicite en mode sequential (Issue #dupond)
2. La détection des références Jinja dans les paramètres
3. Le calcul correct des waves d'exécution

Issue #dupond: Quand execution_mode="sequential" et qu'un step n'a pas de
depends_on explicite, le DependencyGraph doit ajouter une dépendance implicite
sur le step précédent pour garantir l'ordre d'exécution.
"""

import pytest

from src.domains.agents.orchestration.dependency_graph import DependencyGraph
from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def simple_sequential_plan():
    """Plan séquentiel simple avec 3 steps sans depends_on explicite."""
    return ExecutionPlan(
        user_id="user_123",
        session_id="session_456",
        execution_mode="sequential",
        steps=[
            ExecutionStep(
                step_id="search",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",
                tool_name="search_contacts_tool",
                parameters={"query": "dupond"},
                description="Search contacts",
            ),
            ExecutionStep(
                step_id="group",
                step_type=StepType.TOOL,
                agent_name="query_agent",
                tool_name="local_query_engine_tool",
                parameters={"query": {"operation": "group", "target_type": "CONTACT"}},
                description="Group by address",
                # NO depends_on - should be added implicitly
            ),
            ExecutionStep(
                step_id="details",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",
                tool_name="get_contact_details_tool",
                parameters={
                    "resource_names": "{% for g in steps.group.groups %}{{ g.resource_name }}{% endfor %}"
                },
                description="Get details",
                # Has Jinja reference to steps.group - should detect dependency
            ),
        ],
    )


@pytest.fixture
def plan_with_explicit_deps():
    """Plan avec depends_on explicites."""
    return ExecutionPlan(
        user_id="user_123",
        session_id="session_456",
        execution_mode="sequential",
        steps=[
            ExecutionStep(
                step_id="step_a",
                step_type=StepType.TOOL,
                agent_name="test_agent",
                tool_name="tool_a",
                parameters={"x": "1"},
                description="Step A",
            ),
            ExecutionStep(
                step_id="step_b",
                step_type=StepType.TOOL,
                agent_name="test_agent",
                tool_name="tool_b",
                parameters={"y": "$steps.step_a.result"},
                depends_on=["step_a"],  # Explicit dependency
                description="Step B",
            ),
        ],
    )


@pytest.fixture
def parallel_plan():
    """Plan parallèle sans chaînage implicite."""
    return ExecutionPlan(
        user_id="user_123",
        session_id="session_456",
        execution_mode="parallel",  # Parallel mode - no implicit chaining
        steps=[
            ExecutionStep(
                step_id="search_1",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",
                tool_name="search_contacts_tool",
                parameters={"query": "alice"},
                description="Search Alice",
            ),
            ExecutionStep(
                step_id="search_2",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",
                tool_name="search_contacts_tool",
                parameters={"query": "bob"},
                description="Search Bob",
                # NO depends_on - should remain independent in parallel mode
            ),
        ],
    )


# ============================================================================
# Tests Sequential Mode Implicit Chaining (Issue #dupond)
# ============================================================================


class TestSequentialImplicitChaining:
    """Tests for sequential mode implicit dependency chaining."""

    def test_sequential_mode_adds_implicit_deps(self, simple_sequential_plan):
        """Test that sequential mode adds implicit dependencies for steps without deps.

        In the plan:
        - search (step 0): no deps → Wave 0
        - group (step 1): no explicit deps → should depend on search (implicit)
        - details (step 2): has Jinja ref to group → should depend on group

        Without implicit chaining, group would run in parallel with search!
        """
        graph = DependencyGraph(simple_sequential_plan)

        # Check dependencies were added
        assert "search" in graph.dependencies.get(
            "group", set()
        ), "group should have implicit dependency on search"

    def test_sequential_mode_waves_are_correct(self, simple_sequential_plan):
        """Test that waves are calculated correctly with implicit deps."""
        graph = DependencyGraph(simple_sequential_plan)
        waves = graph.compute_all_waves()

        # Should have 3 waves (one per step, sequential)
        assert len(waves) == 3, f"Expected 3 waves, got {len(waves)}: {waves}"

        # Wave 0: search only
        assert waves[0] == {"search"}, f"Wave 0 should be {{'search'}}, got {waves[0]}"

        # Wave 1: group only (depends on search)
        assert waves[1] == {"group"}, f"Wave 1 should be {{'group'}}, got {waves[1]}"

        # Wave 2: details only (depends on group via Jinja)
        assert waves[2] == {"details"}, f"Wave 2 should be {{'details'}}, got {waves[2]}"

    def test_explicit_deps_preserved(self, plan_with_explicit_deps):
        """Test that explicit depends_on is preserved and not duplicated."""
        graph = DependencyGraph(plan_with_explicit_deps)

        # step_b should depend on step_a (explicit)
        assert "step_a" in graph.dependencies.get("step_b", set())

        # step_a should have no dependencies
        assert len(graph.dependencies.get("step_a", set())) == 0

    def test_parallel_mode_no_implicit_chaining(self, parallel_plan):
        """Test that parallel mode does NOT add implicit dependencies."""
        graph = DependencyGraph(parallel_plan)

        # search_2 should NOT have implicit dependency on search_1
        assert "search_1" not in graph.dependencies.get(
            "search_2", set()
        ), "Parallel mode should not add implicit dependencies"

        # Both should be in wave 0 (parallel)
        waves = graph.compute_all_waves()
        assert len(waves) == 1, "Parallel independent steps should be in one wave"
        assert waves[0] == {"search_1", "search_2"}


# ============================================================================
# Tests Jinja Reference Detection
# ============================================================================


class TestJinjaReferenceDetection:
    """Tests for Jinja template reference detection in parameters."""

    def test_detects_jinja_block_reference(self):
        """Test detection of {% %} Jinja block references."""
        plan = ExecutionPlan(
            user_id="user_123",
            steps=[
                ExecutionStep(
                    step_id="search",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="search_tool",
                    parameters={"query": "test"},
                ),
                ExecutionStep(
                    step_id="process",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="process_tool",
                    parameters={
                        "items": "{% for item in steps.search.results %}{{ item.id }}{% endfor %}"
                    },
                ),
            ],
        )

        graph = DependencyGraph(plan)

        # process should depend on search via Jinja reference
        assert "search" in graph.dependencies.get(
            "process", set()
        ), "Should detect Jinja block reference to steps.search"

    def test_detects_jinja_expression_reference(self):
        """Test detection of {{ }} Jinja expression references."""
        plan = ExecutionPlan(
            user_id="user_123",
            steps=[
                ExecutionStep(
                    step_id="resolve",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="resolve_tool",
                    parameters={"ref": "first"},
                ),
                ExecutionStep(
                    step_id="details",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="details_tool",
                    parameters={"id": "{{ steps.resolve.item.id }}"},
                ),
            ],
        )

        graph = DependencyGraph(plan)

        # details should depend on resolve via Jinja expression
        assert "resolve" in graph.dependencies.get(
            "details", set()
        ), "Should detect Jinja expression reference to steps.resolve"

    def test_detects_dollar_reference(self):
        """Test detection of $steps.X references (existing behavior)."""
        plan = ExecutionPlan(
            user_id="user_123",
            steps=[
                ExecutionStep(
                    step_id="step_a",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="tool_a",
                    parameters={"x": "1"},
                ),
                ExecutionStep(
                    step_id="step_b",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="tool_b",
                    parameters={"y": "$steps.step_a.output"},
                ),
            ],
        )

        graph = DependencyGraph(plan)

        # step_b should depend on step_a via $steps reference
        assert "step_a" in graph.dependencies.get("step_b", set()), "Should detect $steps reference"

    def test_detects_multiple_references(self):
        """Test detection of multiple step references in same parameter."""
        plan = ExecutionPlan(
            user_id="user_123",
            steps=[
                ExecutionStep(
                    step_id="search",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="search_tool",
                    parameters={"q": "test"},
                ),
                ExecutionStep(
                    step_id="filter",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="filter_tool",
                    parameters={"q": "test"},
                ),
                ExecutionStep(
                    step_id="combine",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="combine_tool",
                    parameters={
                        "items": "{% for s in steps.search.items %}{{ s }}{% endfor %}{% for f in steps.filter.items %}{{ f }}{% endfor %}"
                    },
                ),
            ],
        )

        graph = DependencyGraph(plan)

        # combine should depend on both search and filter
        combine_deps = graph.dependencies.get("combine", set())
        assert "search" in combine_deps, "Should detect reference to steps.search"
        assert "filter" in combine_deps, "Should detect reference to steps.filter"


# ============================================================================
# Tests Edge Cases
# ============================================================================


class TestDependencyGraphEdgeCases:
    """Edge cases for dependency graph."""

    def test_empty_plan(self):
        """Test handling of empty plan.

        Note: ExecutionPlan requires needs_clarification=True when steps is empty.
        """
        plan = ExecutionPlan(
            user_id="user_123",
            steps=[],
            metadata={"needs_clarification": True},  # Required for empty steps
        )
        graph = DependencyGraph(plan)

        waves = graph.compute_all_waves()
        assert waves == []

    def test_single_step(self):
        """Test plan with single step."""
        plan = ExecutionPlan(
            user_id="user_123",
            steps=[
                ExecutionStep(
                    step_id="only_step",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="tool",
                    parameters={"x": "1"},
                ),
            ],
        )

        graph = DependencyGraph(plan)
        waves = graph.compute_all_waves()

        assert len(waves) == 1
        assert waves[0] == {"only_step"}

    def test_already_has_dependency_no_duplicate(self):
        """Test that step with existing dependency doesn't get duplicate implicit dep."""
        plan = ExecutionPlan(
            user_id="user_123",
            execution_mode="sequential",
            steps=[
                ExecutionStep(
                    step_id="step_a",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="tool_a",
                    parameters={"x": "1"},
                ),
                ExecutionStep(
                    step_id="step_b",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="tool_b",
                    parameters={"y": "$steps.step_a.result"},  # Has reference
                ),
            ],
        )

        graph = DependencyGraph(plan)

        # step_b has $steps.step_a reference, so it already has dependency
        # Sequential implicit chaining should NOT add duplicate
        step_b_deps = graph.dependencies.get("step_b", set())
        assert step_b_deps == {"step_a"}, f"Should have exactly one dependency, got: {step_b_deps}"


# ============================================================================
# Tests FOR_EACH Pattern Expansion (plan_planner.md Section 6.2)
# ============================================================================


class TestForEachExpansion:
    """Tests for for_each pattern expansion."""

    @pytest.fixture
    def for_each_plan(self):
        """Plan with for_each step."""
        return ExecutionPlan(
            user_id="user_123",
            session_id="session_456",
            execution_mode="parallel",
            steps=[
                ExecutionStep(
                    step_id="get_contacts",
                    step_type=StepType.TOOL,
                    agent_name="contacts_agent",
                    tool_name="get_contacts_tool",
                    parameters={"query": "group:family"},
                    description="Get all family contacts",
                ),
                ExecutionStep(
                    step_id="send_emails",
                    step_type=StepType.TOOL,
                    agent_name="email_agent",
                    tool_name="send_email_tool",
                    parameters={
                        "to": "$item.emailAddresses[0].value",
                        "subject": "Hello $item.displayName",
                        "body": "Test message",
                    },
                    depends_on=["get_contacts"],
                    description="Send email to each contact",
                    for_each="$steps.get_contacts.contacts",
                    for_each_max=10,
                    on_item_error="continue",
                ),
            ],
        )

    def test_for_each_step_detection(self, for_each_plan):
        """Test that for_each step is correctly detected."""
        _ = DependencyGraph(for_each_plan)  # Initialize graph (side effect: validates plan)

        # Check step is marked as for_each
        send_step = for_each_plan.steps[1]
        assert send_step.is_for_each_step is True
        assert send_step.for_each == "$steps.get_contacts.contacts"

    def test_for_each_expansion_basic(self, for_each_plan):
        """Test basic for_each expansion with mock data."""
        graph = DependencyGraph(for_each_plan)

        # Simulate provider step results
        step_results = {
            "get_contacts": {
                "contacts": [
                    {"displayName": "Alice", "emailAddresses": [{"value": "alice@example.com"}]},
                    {"displayName": "Bob", "emailAddresses": [{"value": "bob@example.com"}]},
                    {
                        "displayName": "Charlie",
                        "emailAddresses": [{"value": "charlie@example.com"}],
                    },
                ]
            }
        }

        expanded_steps, expansion_map = graph.expand_for_each_steps(step_results)

        # Should have 4 steps: 1 original + 3 expanded (provider + 3 items)
        assert len(expanded_steps) == 4

        # Original step should not have for_each anymore
        assert expansion_map["send_emails"] == [
            "send_emails_item_0",
            "send_emails_item_1",
            "send_emails_item_2",
        ]

    def test_for_each_expansion_with_max_limit(self, for_each_plan):
        """Test that for_each_max limits expansion."""
        graph = DependencyGraph(for_each_plan)

        # Create 15 items but limit is 10
        step_results = {
            "get_contacts": {
                "contacts": [
                    {
                        "displayName": f"Person {i}",
                        "emailAddresses": [{"value": f"p{i}@example.com"}],
                    }
                    for i in range(15)
                ]
            }
        }

        expanded_steps, expansion_map = graph.expand_for_each_steps(step_results)

        # Should have 11 steps: 1 original + 10 expanded (capped by for_each_max)
        assert len(expanded_steps) == 11
        assert len(expansion_map["send_emails"]) == 10

    def test_for_each_expansion_empty_array(self, for_each_plan):
        """Test expansion with empty array."""
        graph = DependencyGraph(for_each_plan)

        step_results = {"get_contacts": {"contacts": []}}  # Empty array

        expanded_steps, expansion_map = graph.expand_for_each_steps(step_results)

        # Should have 1 step: just the original provider
        assert len(expanded_steps) == 1
        assert expansion_map["send_emails"] == []

    def test_item_substitution_in_params(self, for_each_plan):
        """Test $item substitution in expanded step parameters."""
        graph = DependencyGraph(for_each_plan)

        item = {"displayName": "Alice", "emailAddresses": [{"value": "alice@example.com"}]}
        params = {
            "to": "$item.emailAddresses[0].value",
            "subject": "Hello",
            "name": "$item.displayName",
        }

        substituted = graph._substitute_item_in_params(params, item, 0)

        assert substituted["to"] == "alice@example.com"
        assert substituted["name"] == "Alice"

    def test_item_index_substitution(self, for_each_plan):
        """Test $item_index substitution."""
        graph = DependencyGraph(for_each_plan)

        item = {"id": "123"}
        params = {"item_id": "$item.id", "position": "$item_index"}

        substituted = graph._substitute_item_in_params(params, item, 5)

        assert substituted["item_id"] == "123"
        assert substituted["position"] == 5


class TestForEachReferenceResolution:
    """Tests for for_each reference resolution."""

    @pytest.fixture
    def basic_plan(self):
        """Simple plan for reference testing."""
        return ExecutionPlan(
            user_id="user_123",
            steps=[
                ExecutionStep(
                    step_id="search",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="search_tool",
                    parameters={"q": "test"},
                ),
                ExecutionStep(
                    step_id="process",
                    step_type=StepType.TOOL,
                    agent_name="test",
                    tool_name="process_tool",
                    parameters={"data": "$item.field"},
                    for_each="$steps.search.results",
                    depends_on=["search"],
                ),
            ],
        )

    def test_resolve_simple_reference(self, basic_plan):
        """Test resolving simple for_each reference."""
        graph = DependencyGraph(basic_plan)

        step_results = {"search": {"results": [{"field": "a"}, {"field": "b"}, {"field": "c"}]}}

        items = graph._resolve_for_each_reference("$steps.search.results", step_results)

        assert len(items) == 3
        assert items[0]["field"] == "a"
        assert items[1]["field"] == "b"
        assert items[2]["field"] == "c"

    def test_resolve_nested_reference(self, basic_plan):
        """Test resolving nested field path."""
        graph = DependencyGraph(basic_plan)

        step_results = {"search": {"data": {"items": [{"id": 1}, {"id": 2}]}}}

        items = graph._resolve_for_each_reference("$steps.search.data.items", step_results)

        assert len(items) == 2
        assert items[0]["id"] == 1

    def test_resolve_invalid_reference(self, basic_plan):
        """Test handling of invalid reference."""
        graph = DependencyGraph(basic_plan)

        step_results = {"other_step": {"results": []}}

        # Reference points to non-existent step
        items = graph._resolve_for_each_reference("$steps.search.results", step_results)

        assert items == []

    def test_resolve_with_star_notation(self, basic_plan):
        """Test reference with [*] notation."""
        graph = DependencyGraph(basic_plan)

        step_results = {"search": {"results": [{"val": "x"}, {"val": "y"}]}}

        # [*] should be stripped and array returned
        items = graph._resolve_for_each_reference("$steps.search.results[*]", step_results)

        assert len(items) == 2
