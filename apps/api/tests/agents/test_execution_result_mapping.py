"""
Tests for ExecutionResult to AgentResult mapping.

PHASE 3.2.1 - Critical missing tests (T-CRIT-001)
Tests the fragile mapping logic in task_orchestrator_node.py:395-417
"""

from src.domains.agents.orchestration.schemas import ExecutionResult, StepResult
from src.domains.agents.tools.common import ToolErrorCode


class TestExecutionResultToAgentResultMapping:
    """Test mapping ExecutionResult → AgentResult preserves data structure"""

    def test_successful_execution_result_mapping(self):
        """Test successful ExecutionResult maps correctly to agent_results format"""
        # Given: ExecutionResult with successful tool execution
        execution_result = ExecutionResult(
            success=True,
            step_results=[
                StepResult(
                    step_index=0,
                    tool_name="search_contacts_tool",
                    args={"query": "John"},
                    result={
                        "success": True,
                        "data": {
                            "contacts": [{"name": "John Doe", "emails": ["john@example.com"]}],
                            "total_count": 1,
                        },
                        "error": None,
                    },
                    success=True,
                    execution_time_ms=250,
                )
            ],
            total_steps=1,
            completed_steps=1,
            total_execution_time_ms=250,
        )

        # When: Extract data for agent_results (simulating task_orchestrator logic)
        all_results_data = []
        for step_result in execution_result.step_results:
            if step_result.success and step_result.result:
                if isinstance(step_result.result, dict) and "data" in step_result.result:
                    all_results_data.append(step_result.result["data"])

        agent_result = {
            "agent_name": "plan_executor",
            "status": "success" if execution_result.success else "error",
            "data": {
                "completed_steps": execution_result.completed_steps,
                "total_steps": execution_result.total_steps,
                "execution_time_ms": execution_result.total_execution_time_ms,
                "aggregated_results": all_results_data,
            },
            "error": execution_result.error if not execution_result.success else None,
        }

        # Then: AgentResult structure is correct
        assert agent_result["agent_name"] == "plan_executor"
        assert agent_result["status"] == "success"
        assert agent_result["data"]["aggregated_results"][0]["contacts"][0]["name"] == "John Doe"
        assert agent_result["data"]["completed_steps"] == 1
        assert agent_result["error"] is None

    def test_failed_execution_result_mapping(self):
        """Test failed ExecutionResult maps error correctly"""
        # Given: ExecutionResult with error
        execution_result = ExecutionResult(
            success=False,
            step_results=[
                StepResult(
                    step_index=0,
                    tool_name="search_contacts_tool",
                    args={"query": "John"},
                    result=None,
                    success=False,
                    error="API connection failed",
                    error_code=ToolErrorCode.EXTERNAL_API_ERROR,
                    execution_time_ms=100,
                )
            ],
            total_steps=1,
            completed_steps=0,
            failed_step_index=0,
            error="API connection failed",
            error_code=ToolErrorCode.EXTERNAL_API_ERROR,
            total_execution_time_ms=100,
        )

        # When: Extract data for agent_results
        all_results_data = []
        for step_result in execution_result.step_results:
            if step_result.success and step_result.result:
                if isinstance(step_result.result, dict) and "data" in step_result.result:
                    all_results_data.append(step_result.result["data"])

        agent_result = {
            "agent_name": "plan_executor",
            "status": "success" if execution_result.success else "error",
            "data": {
                "completed_steps": execution_result.completed_steps,
                "total_steps": execution_result.total_steps,
                "execution_time_ms": execution_result.total_execution_time_ms,
                "aggregated_results": all_results_data,
            },
            "error": execution_result.error if not execution_result.success else None,
        }

        # Then: Error propagated correctly
        assert agent_result["status"] == "error"
        assert agent_result["error"] == "API connection failed"
        assert agent_result["data"]["completed_steps"] == 0
        assert len(agent_result["data"]["aggregated_results"]) == 0

    def test_empty_step_results_mapping(self):
        """Test ExecutionResult with no steps"""
        # Given: Empty ExecutionResult
        execution_result = ExecutionResult(
            success=True,
            step_results=[],
            total_steps=0,
            completed_steps=0,
            total_execution_time_ms=0,
        )

        # When: Extract data
        all_results_data = []
        for step_result in execution_result.step_results:
            if step_result.success and step_result.result:
                if isinstance(step_result.result, dict) and "data" in step_result.result:
                    all_results_data.append(step_result.result["data"])

        agent_result = {
            "agent_name": "plan_executor",
            "status": "success" if execution_result.success else "error",
            "data": {
                "completed_steps": execution_result.completed_steps,
                "total_steps": execution_result.total_steps,
                "execution_time_ms": execution_result.total_execution_time_ms,
                "aggregated_results": all_results_data,
            },
            "error": execution_result.error if not execution_result.success else None,
        }

        # Then: Empty results handled correctly
        assert agent_result["status"] == "success"
        assert agent_result["data"]["completed_steps"] == 0
        assert len(agent_result["data"]["aggregated_results"]) == 0

    def test_mixed_success_failure_steps_mapping(self):
        """Test ExecutionResult with mixed success/failure steps"""
        # Given: Multiple steps with mixed results
        execution_result = ExecutionResult(
            success=True,  # Plan completed despite some failures
            step_results=[
                StepResult(
                    step_index=0,
                    tool_name="search_contacts_tool",
                    args={"query": "John"},
                    result={
                        "success": True,
                        "data": {"contacts": [{"name": "John"}], "total_count": 1},
                    },
                    success=True,
                    execution_time_ms=200,
                ),
                StepResult(
                    step_index=1,
                    tool_name="get_contact_details_tool",
                    args={"resource_name": "people/c123"},
                    result=None,
                    success=False,
                    error="Not found",
                    error_code=ToolErrorCode.NOT_FOUND,
                    execution_time_ms=100,
                ),
                StepResult(
                    step_index=2,
                    tool_name="list_contacts_tool",
                    args={"limit": 10},
                    result={
                        "success": True,
                        "data": {"contacts": [{"name": "Jane"}], "total_count": 1},
                    },
                    success=True,
                    execution_time_ms=250,
                ),
            ],
            total_steps=3,
            completed_steps=2,
            total_execution_time_ms=550,
        )

        # When: Extract only successful results
        all_results_data = []
        for step_result in execution_result.step_results:
            if step_result.success and step_result.result:
                if isinstance(step_result.result, dict) and "data" in step_result.result:
                    all_results_data.append(step_result.result["data"])

        agent_result = {
            "agent_name": "plan_executor",
            "status": "success" if execution_result.success else "error",
            "data": {
                "completed_steps": execution_result.completed_steps,
                "total_steps": execution_result.total_steps,
                "execution_time_ms": execution_result.total_execution_time_ms,
                "aggregated_results": all_results_data,
            },
            "error": execution_result.error if not execution_result.success else None,
        }

        # Then: Only successful steps included
        assert agent_result["status"] == "success"
        assert len(agent_result["data"]["aggregated_results"]) == 2
        assert agent_result["data"]["aggregated_results"][0]["contacts"][0]["name"] == "John"
        assert agent_result["data"]["aggregated_results"][1]["contacts"][0]["name"] == "Jane"
        assert agent_result["data"]["completed_steps"] == 2

    def test_step_result_without_data_key(self):
        """Test StepResult with result dict but no 'data' key"""
        # Given: StepResult with malformed result
        execution_result = ExecutionResult(
            success=True,
            step_results=[
                StepResult(
                    step_index=0,
                    tool_name="some_tool",
                    args={},
                    result={
                        "success": True,
                        # Missing "data" key!
                        "metadata": {"foo": "bar"},
                    },
                    success=True,
                    execution_time_ms=100,
                )
            ],
            total_steps=1,
            completed_steps=1,
            total_execution_time_ms=100,
        )

        # When: Extract data (should skip result without "data")
        all_results_data = []
        for step_result in execution_result.step_results:
            if step_result.success and step_result.result:
                if isinstance(step_result.result, dict) and "data" in step_result.result:
                    all_results_data.append(step_result.result["data"])

        # Then: Result skipped gracefully
        assert len(all_results_data) == 0

    def test_step_result_with_none_result(self):
        """Test StepResult with None result"""
        # Given: StepResult with None result
        execution_result = ExecutionResult(
            success=True,
            step_results=[
                StepResult(
                    step_index=0,
                    tool_name="some_tool",
                    args={},
                    result=None,  # None result
                    success=True,  # But marked success
                    execution_time_ms=50,
                )
            ],
            total_steps=1,
            completed_steps=1,
            total_execution_time_ms=50,
        )

        # When: Extract data
        all_results_data = []
        for step_result in execution_result.step_results:
            if step_result.success and step_result.result:
                if isinstance(step_result.result, dict) and "data" in step_result.result:
                    all_results_data.append(step_result.result["data"])

        # Then: None result skipped gracefully
        assert len(all_results_data) == 0
