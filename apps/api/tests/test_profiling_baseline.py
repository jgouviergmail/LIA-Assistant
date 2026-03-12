"""
Test profiling baseline - Trigger profiled functions to collect metrics.

This test file is specifically designed to trigger the 3 instrumented functions
with @profile_performance decorators to collect baseline performance metrics.

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-16
"""

import pytest


@pytest.mark.asyncio
class TestProfilingBaseline:
    """Test profiling baseline collection."""

    async def test_context_store_cleanup_profiling(self):
        """
        Trigger context_store_cleanup() to collect profiling data.

        Function: domains/agents/context/manager.py:cleanup_session_contexts()
        Decorator: @profile_performance(func_name="context_store_cleanup", log_threshold_ms=100.0)
        Expected P99: < 50ms
        """
        # This test would need to trigger conversation reset or context cleanup
        # For now, we'll skip if the exact integration isn't ready
        pytest.skip("Context cleanup integration test - implement when ready")

    async def test_dependency_graph_reverse_profiling(self):
        """
        Trigger _build_reverse_graph() to collect profiling data.

        Function: domains/agents/orchestration/dependency_graph.py:_build_reverse_graph()
        Decorator: @profile_performance(func_name="dependency_graph_reverse", log_threshold_ms=50.0)
        Expected P99: < 5ms
        """
        from src.domains.agents.orchestration.dependency_graph import DependencyGraph
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )

        # Create ExecutionSteps with proper schema
        steps = [
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="test_agent",
                tool_name="test_tool_1",
                description="Test step 1",
                depends_on=[],
            ),
            ExecutionStep(
                step_id="step_2",
                step_type=StepType.TOOL,
                agent_name="test_agent",
                tool_name="test_tool_2",
                description="Test step 2",
                depends_on=["step_1"],
            ),
            ExecutionStep(
                step_id="step_3",
                step_type=StepType.TOOL,
                agent_name="test_agent",
                tool_name="test_tool_3",
                description="Test step 3",
                depends_on=["step_1", "step_2"],
            ),
            ExecutionStep(
                step_id="step_4",
                step_type=StepType.TOOL,
                agent_name="test_agent",
                tool_name="test_tool_4",
                description="Test step 4",
                depends_on=["step_2"],
            ),
            ExecutionStep(
                step_id="step_5",
                step_type=StepType.TOOL,
                agent_name="test_agent",
                tool_name="test_tool_5",
                description="Test step 5",
                depends_on=["step_3", "step_4"],
            ),
        ]

        # Create ExecutionPlan
        plan = ExecutionPlan(
            plan_id="test_plan",
            user_id="test_user",
            session_id="test_session",
            user_query="Test query for profiling",
            steps=steps,
            total_steps=5,
        )

        # Trigger _build_reverse_graph() multiple times for profiling
        # The reverse graph is built during initialization
        for _ in range(10):
            graph = DependencyGraph(plan)
            # Validate it works by checking waves
            waves = graph.compute_all_waves()
            assert len(waves) > 0
            assert "step_1" in waves[0]  # First wave should be step_1

    async def test_format_agent_results_profiling(self):
        """
        Trigger format_agent_results_for_prompt() to collect profiling data.

        Function: domains/agents/nodes/response_node.py:format_agent_results_for_prompt()
        Decorator: @profile_performance(func_name="format_agent_results", log_threshold_ms=50.0)
        Expected P99: < 20ms
        """
        # Sample agent results with correct format (composite key: turn_id:agent_name)
        from src.core.field_names import FIELD_STATUS
        from src.domains.agents.nodes.response_node import format_agent_results_for_prompt

        agent_results = {
            "1:contacts_agent": {
                FIELD_STATUS: "success",
                "data": {
                    "total_count": 2,
                    "contacts": [
                        {
                            "name": "Jean Dupont",
                            "email": "jean.dupont@example.com",
                            "phone": "+33612345678",
                        },
                        {
                            "name": "Marie Martin",
                            "email": "marie.martin@example.com",
                            "phone": "+33687654321",
                        },
                    ],
                },
            },
        }

        current_turn_id = 1

        # Trigger format_agent_results_for_prompt() multiple times
        for _ in range(10):
            formatted = format_agent_results_for_prompt(agent_results, current_turn_id)

            # Validate output (success emoji + agent name)
            assert isinstance(formatted, str)
            assert len(formatted) > 0
            assert "✅" in formatted or "contacts_agent" in formatted


@pytest.mark.asyncio
class TestProfilingStressTest:
    """Stress test profiled functions with larger datasets."""

    async def test_dependency_graph_large_dataset(self):
        """Test dependency graph with larger dataset (20 steps)."""
        from src.domains.agents.orchestration.dependency_graph import DependencyGraph
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )

        # Create a larger dependency graph with proper schemas
        steps = []
        for i in range(20):
            deps = []
            if i > 0:
                # Each step depends on 1-3 previous steps
                for j in range(max(0, i - 3), i):
                    if j % 2 == 0:  # Sparse dependencies
                        deps.append(f"step_{j}")

            steps.append(
                ExecutionStep(
                    step_id=f"step_{i}",
                    step_type=StepType.TOOL,
                    agent_name="test_agent",
                    tool_name=f"test_tool_{i}",
                    description=f"Test step {i}",
                    depends_on=deps,
                )
            )

        plan = ExecutionPlan(
            plan_id="stress_test_plan",
            user_id="test_user",
            session_id="test_session",
            user_query="Stress test query",
            steps=steps,
            total_steps=20,
        )

        # Build and validate
        graph = DependencyGraph(plan)
        waves = graph.compute_all_waves()

        assert len(waves) > 0
        # First wave should be step_0 (no dependencies)
        assert "step_0" in waves[0]

    async def test_format_agent_results_large_dataset(self):
        """Test format agent results with larger dataset (10 agents × 5 contacts)."""
        from src.core.field_names import FIELD_STATUS
        from src.domains.agents.nodes.response_node import format_agent_results_for_prompt

        # Larger dataset - 10 agents with 5 contacts each
        agent_results = {}
        for i in range(10):
            agent_results[f"1:contacts_agent_{i}"] = {
                FIELD_STATUS: "success",
                "data": {
                    "total_count": 5,
                    "contacts": [
                        {
                            "name": f"Contact {i}-{j}",
                            "email": f"contact.{i}.{j}@example.com",
                            "phone": f"+3361234567{i}{j}",
                        }
                        for j in range(5)
                    ],
                },
            }

        current_turn_id = 1

        # Format results
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id)

        # Validate
        assert isinstance(formatted, str)
        assert len(formatted) > 0
        # Should contain success indicators
        assert "✅" in formatted or "contact" in formatted.lower()
