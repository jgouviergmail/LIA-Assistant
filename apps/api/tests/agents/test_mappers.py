"""
Unit tests for orchestration mappers.

Tests the mapping functions that convert between different result formats
in the orchestration layer.

Phase 3.2.3: Tests for map_execution_result_to_agent_result
"""

from src.domains.agents.orchestration.mappers import map_execution_result_to_agent_result
from src.domains.agents.orchestration.schemas import ExecutionResult, StepResult


class TestMapExecutionResultToAgentResult:
    """Tests for map_execution_result_to_agent_result function."""

    def test_successful_execution_with_single_step(self):
        """Test mapping a successful execution with one step."""
        # Given: Successful ExecutionResult with 1 step
        # Note: StepResult.result contains ALREADY EXTRACTED data (not wrapped in success/data)
        # This is because plan_executor extracts the "data" field before storing in StepResult
        step_result = StepResult(
            step_index=0,
            tool_name="search_contacts_tool",
            args={"query": "Jean"},
            success=True,
            result={
                "contacts": [
                    {"name": "Jean", "resource_name": "people/c1"},
                    {"name": "Marie", "resource_name": "people/c2"},
                ],
                "total": 2,
            },
            execution_time_ms=100,
        )

        execution_result = ExecutionResult(
            success=True,
            completed_steps=1,
            total_steps=1,
            step_results=[step_result],
            total_execution_time_ms=100,
        )

        # When: Map to agent_result
        agent_results = map_execution_result_to_agent_result(
            execution_result=execution_result, plan_id="plan123", turn_id=5
        )

        # Then: Correct mapping
        assert len(agent_results) == 1
        assert "5:plan_executor" in agent_results

        agent_result = agent_results["5:plan_executor"]
        assert agent_result["agent_name"] == "plan_executor"
        assert agent_result["status"] == "success"
        assert agent_result["error"] is None

        # When contacts are detected, data is normalized to ContactsResultData format
        data = agent_result["data"]
        assert data["total_count"] == 2  # Normalized contact count
        assert len(data["contacts"]) == 2  # Normalized contacts list
        assert data["contacts"][0]["name"] == "Jean"
        assert data["data_source"] == "api"

    def test_successful_execution_with_multiple_steps(self):
        """Test mapping a successful execution with multiple steps."""
        # Given: Successful ExecutionResult with 3 steps
        # Note: StepResult.result contains ALREADY EXTRACTED data
        step_results = [
            StepResult(
                step_index=0,
                tool_name="search_contacts_tool",
                args={"query": "Jean"},
                success=True,
                result={"contacts": [{"name": "Jean", "resource_name": "people/c1"}]},
                execution_time_ms=50,
            ),
            StepResult(
                step_index=1,
                tool_name="get_context_list",
                args={"domain": "contacts"},
                success=True,
                result={"found": True},  # Non-contacts data
                execution_time_ms=10,
            ),
            StepResult(
                step_index=2,
                tool_name="get_contact_details_tool",
                args={"resource_name": "people/c123"},
                success=True,
                result={
                    "contacts": [
                        {
                            "name": "Jean",
                            "email": "jean@example.com",
                            "resource_name": "people/c123",
                        }
                    ]
                },
                execution_time_ms=150,
            ),
        ]

        execution_result = ExecutionResult(
            success=True,
            completed_steps=3,
            total_steps=3,
            step_results=step_results,
            total_execution_time_ms=210,
        )

        # When: Map to agent_result
        agent_results = map_execution_result_to_agent_result(
            execution_result=execution_result, plan_id="plan456", turn_id=7
        )

        # Then: Contacts are normalized and deduplicated
        agent_result = agent_results["7:plan_executor"]
        assert agent_result["status"] == "success"
        # Contacts are deduplicated by resource_name: people/c1 and people/c123
        assert agent_result["data"]["total_count"] == 2
        assert len(agent_result["data"]["contacts"]) == 2

    def test_failed_execution(self):
        """Test mapping a failed execution."""
        # Given: Failed ExecutionResult
        step_result = StepResult(
            step_index=0,
            tool_name="search_contacts_tool",
            args={"query": "NonExistent"},
            success=False,
            result={"success": False, "error": "NOT_FOUND", "message": "Contact not found"},
            execution_time_ms=50,
        )

        execution_result = ExecutionResult(
            success=False,
            completed_steps=0,
            total_steps=2,
            step_results=[step_result],
            total_execution_time_ms=50,
            error="Step 'search' failed: Contact not found",
        )

        # When: Map to agent_result
        agent_results = map_execution_result_to_agent_result(
            execution_result=execution_result, plan_id="plan789", turn_id=3
        )

        # Then: Status is failed and error is set
        agent_result = agent_results["3:plan_executor"]
        assert agent_result["agent_name"] == "plan_executor"
        assert agent_result["status"] == "failed"
        assert agent_result["error"] == "Step 'search' failed: Contact not found"
        assert agent_result["data"]["completed_steps"] == 0
        assert agent_result["data"]["total_steps"] == 2

    def test_execution_with_no_domain_specific_data(self):
        """Test mapping when step results don't have domain-specific data (contacts/emails)."""
        # Given: Step result with generic data (no contacts/emails)
        step_result = StepResult(
            step_index=0,
            tool_name="list_active_domains",
            args={},
            success=True,
            result={
                "domains": ["contacts", "emails"],
                "message": "OK",
            },  # Generic data, not contacts/emails
            execution_time_ms=10,
        )

        execution_result = ExecutionResult(
            success=True,
            completed_steps=1,
            total_steps=1,
            step_results=[step_result],
            total_execution_time_ms=10,
        )

        # When: Map to agent_result
        agent_results = map_execution_result_to_agent_result(
            execution_result=execution_result, plan_id="plan999", turn_id=1
        )

        # Then: Generic format is used with step_results containing the data
        agent_result = agent_results["1:plan_executor"]
        assert agent_result["status"] == "success"
        # Generic format includes step_results
        assert len(agent_result["data"]["step_results"]) == 1
        assert agent_result["data"]["step_results"][0]["domains"] == ["contacts", "emails"]

    def test_execution_with_failed_steps_mixed(self):
        """Test mapping with mix of successful and failed steps."""
        # Given: ExecutionResult with both successful and failed steps
        # Note: StepResult.result contains ALREADY EXTRACTED data
        step_results = [
            StepResult(
                step_index=0,
                tool_name="search_contacts_tool",
                args={"query": "Jean"},
                success=True,
                result={"contacts": [{"name": "Jean", "resource_name": "people/c1"}]},
                execution_time_ms=50,
            ),
            StepResult(
                step_index=1,
                tool_name="resolve_reference",
                args={"reference": "invalid", "domain": "contacts"},
                success=False,
                result={"error": "VALIDATION_ERROR"},
                execution_time_ms=10,
            ),
        ]

        execution_result = ExecutionResult(
            success=False,
            completed_steps=1,
            total_steps=2,
            step_results=step_results,
            total_execution_time_ms=60,
            error="Step 'check' failed",
        )

        # When: Map to agent_result
        agent_results = map_execution_result_to_agent_result(
            execution_result=execution_result, plan_id="plan111", turn_id=2
        )

        # Then: Only successful steps' contacts data is normalized
        agent_result = agent_results["2:plan_executor"]
        assert agent_result["status"] == "failed"
        # Contacts are normalized from the successful step
        assert agent_result["data"]["total_count"] == 1
        assert agent_result["data"]["contacts"][0]["name"] == "Jean"

    def test_composite_key_format(self):
        """Test that composite key follows the expected format."""
        # Given: ExecutionResult
        execution_result = ExecutionResult(
            success=True,
            completed_steps=1,
            total_steps=1,
            step_results=[],
            total_execution_time_ms=50,
        )

        # When: Map with different turn_ids
        result_turn_5 = map_execution_result_to_agent_result(
            execution_result=execution_result, plan_id="plan1", turn_id=5
        )
        result_turn_10 = map_execution_result_to_agent_result(
            execution_result=execution_result, plan_id="plan2", turn_id=10
        )

        # Then: Composite keys match pattern "{turn_id}:plan_executor"
        assert "5:plan_executor" in result_turn_5
        assert "10:plan_executor" in result_turn_10
        assert result_turn_5["5:plan_executor"]["agent_name"] == "plan_executor"
        assert result_turn_10["10:plan_executor"]["agent_name"] == "plan_executor"

    def test_aggregated_results_structure(self):
        """Test that contacts are normalized with correct structure."""
        # Given: ExecutionResult with contacts data
        # Note: StepResult.result contains ALREADY EXTRACTED data
        step_result = StepResult(
            step_index=0,
            tool_name="get_contact_details_tool",
            args={"resource_name": "people/c123"},
            success=True,
            result={
                "contacts": [
                    {
                        "resource_name": "people/c123",
                        "name": "Jean Dupont",
                        "emails": ["jean@example.com"],
                    }
                ]
            },
            execution_time_ms=100,
        )

        execution_result = ExecutionResult(
            success=True,
            completed_steps=1,
            total_steps=1,
            step_results=[step_result],
            total_execution_time_ms=100,
        )

        # When: Map to agent_result
        agent_results = map_execution_result_to_agent_result(
            execution_result=execution_result, plan_id="plan222", turn_id=4
        )

        # Then: Contacts are normalized in ContactsResultData format
        agent_result = agent_results["4:plan_executor"]
        assert agent_result["data"]["total_count"] == 1
        assert agent_result["data"]["contacts"][0]["resource_name"] == "people/c123"
        assert agent_result["data"]["contacts"][0]["name"] == "Jean Dupont"
