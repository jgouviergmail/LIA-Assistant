"""
E2E Integration Tests for Phase 3.2: Normalization & Validation.

Phase 3.2.7: Tests validating the complete workflow:
- Tool execution → ToolResponse (Pydantic)
- parallel_executor → ExecutionResult (Pydantic)
- Mapper → AgentResult (Pydantic)
- Backward compatibility with existing consumers
- Performance measurement
- Error handling scenarios

These tests ensure that the Pydantic migration works correctly in production scenarios.
"""

import json
import time

import pytest
from pydantic import ValidationError

from src.domains.agents.constants import make_agent_result_key
from src.domains.agents.orchestration.mappers import map_execution_result_to_agent_result
from src.domains.agents.orchestration.schemas import (
    AgentResult,
    ContactsResultData,
    ExecutionResult,
    StepResult,
)
from src.domains.agents.tools.schemas import ToolResponse

pytestmark = pytest.mark.unit


class TestToolResponseToAgentResultWorkflow:
    """Test complete workflow: ToolResponse → ExecutionResult → AgentResult."""

    def test_single_tool_success_workflow(self):
        """
        Test E2E workflow with single successful tool execution.

        Scenario: Tool returns ToolResponse → parallel_executor creates ExecutionResult →
                  Mapper creates AgentResult.
        """
        # Given: Tool returns ToolResponse (migrated tool pattern)
        tool_response = ToolResponse.success_response(
            data={
                "contacts": [{"name": "Jean Dupont", "email": "jean@example.com"}],
                "total_count": 1,
            },
            message="Found 1 contact",
        )

        # When: parallel_executor creates StepResult from tool response
        step_result = StepResult(
            step_index=0,
            tool_name="get_context_list",
            args={"domain": "contacts"},
            result=json.loads(tool_response.model_dump_json()),  # Simulates tool execution
            success=True,
            error=None,
            error_code=None,
            execution_time_ms=150,
            hitl_approved=None,
        )

        # And: parallel_executor creates ExecutionResult
        execution_result = ExecutionResult(
            success=True,
            step_results=[step_result],
            total_steps=1,
            completed_steps=1,
            failed_step_index=None,
            error=None,
            error_code=None,
            total_execution_time_ms=150,
            executed_at="2025-01-01T00:00:00Z",
        )

        # And: Mapper creates AgentResult
        agent_results = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=5,
        )

        # Then: AgentResult structure is correct
        assert make_agent_result_key(5, "plan_executor") in agent_results
        result = agent_results[make_agent_result_key(5, "plan_executor")]

        # Validate AgentResult fields
        assert result["agent_name"] == "plan_executor"
        assert result["status"] == "success"
        assert result["error"] is None
        assert result["duration_ms"] == 150

        # Validate data contains aggregated results
        assert "aggregated_results" in result["data"]
        assert len(result["data"]["aggregated_results"]) == 1
        # `aggregated_results` holds the tool result AS THE EXECUTOR STORED IT:
        # the full ToolResponse envelope, so the payload lives under "data".
        # (A comment in `mappers.py` used to claim the envelope had already
        # been unwrapped — it never was.)
        aggregated = result["data"]["aggregated_results"][0]
        assert aggregated["success"] is True
        assert aggregated["data"]["contacts"][0]["name"] == "Jean Dupont"

    def test_multiple_tools_aggregation_workflow(self):
        """
        Test E2E workflow with multiple tool executions aggregated.

        Scenario: Multiple tools return ToolResponse → Results are aggregated.
        """
        # Given: Multiple tool responses
        tool_response_1 = ToolResponse.success_response(
            data={"contacts": [{"name": "Jean"}], "total_count": 1}
        )
        tool_response_2 = ToolResponse.success_response(
            data={"contacts": [{"name": "Marie"}], "total_count": 1}
        )

        # When: parallel_executor creates multiple StepResults
        step_results = [
            StepResult(
                step_index=0,
                tool_name="search_contacts_tool",
                args={"query": "Jean"},
                result=json.loads(tool_response_1.model_dump_json()),
                success=True,
                error=None,
                error_code=None,
                execution_time_ms=100,
                hitl_approved=None,
            ),
            StepResult(
                step_index=1,
                tool_name="search_contacts_tool",
                args={"query": "Marie"},
                result=json.loads(tool_response_2.model_dump_json()),
                success=True,
                error=None,
                error_code=None,
                execution_time_ms=120,
                hitl_approved=None,
            ),
        ]

        execution_result = ExecutionResult(
            success=True,
            step_results=step_results,
            total_steps=2,
            completed_steps=2,
            failed_step_index=None,
            error=None,
            error_code=None,
            total_execution_time_ms=220,
            executed_at="2025-01-01T00:00:00Z",
        )

        # And: Mapper aggregates results
        agent_results = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan456",
            turn_id=10,
        )

        # Then: Results are aggregated
        result = agent_results[make_agent_result_key(10, "plan_executor")]
        assert result["status"] == "success"
        assert result["data"]["completed_steps"] == 2
        assert result["data"]["total_steps"] == 2

        # Verify aggregation
        aggregated = result["data"]["aggregated_results"]
        assert len(aggregated) == 2
        assert aggregated[0]["data"]["contacts"][0]["name"] == "Jean"
        assert aggregated[1]["data"]["contacts"][0]["name"] == "Marie"

    def test_tool_error_propagation_workflow(self):
        """
        Test E2E workflow when tool returns error ToolResponse.

        Scenario: Tool fails → ToolResponse.error_response() → ExecutionResult.success=False
        """
        # Given: Tool returns error response
        tool_error_response = ToolResponse.error_response(
            error="NOT_FOUND", message="Contact not found"
        )

        # When: parallel_executor creates StepResult with error
        step_result = StepResult(
            step_index=0,
            tool_name="get_contact_details_tool",
            args={"contact_id": "invalid123"},
            result=json.loads(tool_error_response.model_dump_json()),
            success=False,
            error="Contact not found",
            error_code="NOT_FOUND",
            execution_time_ms=50,
            hitl_approved=None,
        )

        execution_result = ExecutionResult(
            success=False,
            step_results=[step_result],
            total_steps=1,
            completed_steps=0,  # Failed before completion
            failed_step_index=0,
            error="Step 0 failed: Contact not found",
            error_code="NOT_FOUND",
            total_execution_time_ms=50,
            executed_at="2025-01-01T00:00:00Z",
        )

        # And: Mapper creates AgentResult with error
        agent_results = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan789",
            turn_id=15,
        )

        # Then: AgentResult reflects failure
        result = agent_results[make_agent_result_key(15, "plan_executor")]
        assert result["status"] == "failed"
        assert result["error"] == "Step 0 failed: Contact not found"
        assert result["data"]["completed_steps"] == 0
        assert result["data"]["total_steps"] == 1


class TestPydanticRuntimeValidation:
    """Test Pydantic runtime validation catches errors."""

    def test_tool_response_validates_required_fields(self):
        """Test ToolResponse requires success field."""
        # When/Then: Missing required field raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            ToolResponse()  # Missing 'success'

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("success",) for e in errors)

    def test_agent_result_validates_status_literal(self):
        """Test AgentResult only accepts valid status values."""
        # When/Then: Invalid status literal raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            AgentResult(
                agent_name="test_agent",
                status="invalid_status",  # Not in Literal
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("status",) for e in errors)

    def test_execution_result_validates_structure(self):
        """Test ExecutionResult validates step_results structure."""
        # Given: Invalid step result (missing required fields)
        with pytest.raises(ValidationError) as exc_info:
            ExecutionResult(
                success=True,
                step_results=[{"invalid": "structure"}],  # Not a StepResult
                total_steps=1,
                completed_steps=1,
            )

        # Then: Pydantic catches the error
        assert exc_info.value.errors()

    def test_contacts_result_data_validates_data_source_literal(self):
        """Test ContactsResultData only accepts 'api' or 'cache'."""
        # When/Then: Invalid data_source raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            ContactsResultData(
                total_count=5,
                data_source="database",  # Not in Literal["api", "cache"]
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("data_source",) for e in errors)


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    def test_agent_result_dict_format_preserved(self):
        """`model_dump()` keeps a producer's dict payload intact.

        This is the invariant `AgentResultData(extra="forbid")` exists to
        protect, in the schema's own words: without it "a dict with arbitrary
        keys could be coerced to a domain-specific model … causing the dict's
        actual data (like step_results) to be silently discarded". So the
        payload here is the one a real producer emits — the plan-executor
        shape — not a one-key stub.
        """
        # Given: Pydantic AgentResult holding a plan-executor payload
        payload = {
            "plan_id": "plan123",
            "completed_steps": 2,
            "total_steps": 2,
            "step_results": [{"step_id": "s1", "success": True}],
            "aggregated_results": [{"success": True, "data": {"contacts": []}}],
        }
        agent_result = AgentResult(
            agent_name="contacts_agent",
            status="success",
            data=payload,
            error=None,
            tokens_in=100,
            tokens_out=200,
            duration_ms=500,
        )

        # When: Serialize to dict
        result_dict = agent_result.model_dump()

        # Then: Dict format matches TypedDict expectations
        assert result_dict["agent_name"] == "contacts_agent"
        assert result_dict["status"] == "success"
        assert result_dict["data"] == payload  # untouched, no field invented
        assert result_dict["error"] is None
        assert result_dict["tokens_in"] == 100
        assert result_dict["tokens_out"] == 200
        assert result_dict["duration_ms"] == 500

    def test_a_dict_matching_a_domain_schema_is_absorbed_by_it(self):
        """Characterization: `extra="forbid"` cannot disambiguate a subset payload.

        `EmailsResultData` requires only `total`; everything else is defaulted.
        A payload of exactly `{"total": 10}` is therefore a VALID member of the
        union and is promoted to it, gaining `emails: []`, `data_source`, a
        timestamp… — fields the producer never set. No real producer emits that
        shape (plan executor, contacts and places payloads all carry keys no
        domain model declares, which `extra="forbid"` rejects), so this is a
        documented limit of the union, not a live defect. It is pinned here so
        that adding a domain model with NO required field — which would swallow
        `{}` and every dict — fails loudly instead of silently.
        """
        absorbed = AgentResult(
            agent_name="emails_agent", status="success", data={"total": 10}
        ).model_dump()

        assert absorbed["data"]["total"] == 10
        assert absorbed["data"]["result_type"] == "emails"
        assert absorbed["data"]["emails"] == []

        # The guard that keeps real payloads out of the domain models.
        untouched = AgentResult(
            agent_name="emails_agent", status="success", data={"total": 10, "unknown_key": 1}
        ).model_dump()
        assert untouched["data"] == {"total": 10, "unknown_key": 1}

    def test_tool_response_json_format_preserved(self):
        """Test ToolResponse.model_dump_json() matches legacy json.dumps() format."""
        # Given: ToolResponse
        response = ToolResponse.success_response(data={"count": 5}, message="Success")

        # When: Serialize to JSON
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)

        # Then: Format matches legacy {"success": bool, "data": {...}, "message": str}
        assert parsed["success"] is True
        assert parsed["data"] == {"count": 5}
        assert parsed["message"] == "Success"
        assert "error" not in parsed  # None excluded by default

    def test_mapper_output_format_unchanged(self):
        """Test mapper output format is compatible with state graph."""
        # Given: ExecutionResult
        execution_result = ExecutionResult(
            success=True,
            step_results=[
                StepResult(
                    step_index=0,
                    tool_name="test_tool",
                    args={},
                    result={"success": True, "data": {"test": "value"}},
                    success=True,
                    error=None,
                    error_code=None,
                    execution_time_ms=100,
                    hitl_approved=None,
                )
            ],
            total_steps=1,
            completed_steps=1,
            failed_step_index=None,
            error=None,
            error_code=None,
            total_execution_time_ms=100,
            executed_at="2025-01-01T00:00:00Z",
        )

        # When: Mapper creates agent_results
        agent_results = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan_test",
            turn_id=20,
        )

        # Then: Output is dict (not Pydantic model)
        assert isinstance(agent_results, dict)
        assert make_agent_result_key(20, "plan_executor") in agent_results

        # And: Inner result is dict (model_dump() was called)
        result = agent_results[make_agent_result_key(20, "plan_executor")]
        assert isinstance(result, dict)
        assert "agent_name" in result
        assert "status" in result


class TestPerformanceOverhead:
    """Test Pydantic validation performance overhead."""

    def test_tool_response_creation_performance(self):
        """Measure ToolResponse creation overhead vs raw dict."""
        iterations = 1000

        # Baseline: Raw dict creation
        start_raw = time.perf_counter()
        for _ in range(iterations):
            raw_dict = {
                "success": True,
                "data": {"contacts": [{"name": "Test"}]},
                "message": "Success",
            }
            json.dumps(raw_dict)
        raw_time = time.perf_counter() - start_raw

        # Pydantic: ToolResponse creation
        start_pydantic = time.perf_counter()
        for _ in range(iterations):
            response = ToolResponse.success_response(
                data={"contacts": [{"name": "Test"}]}, message="Success"
            )
            response.model_dump_json()
        pydantic_time = time.perf_counter() - start_pydantic

        # Then: Overhead should be reasonable (< 10x slower)
        overhead_ratio = pydantic_time / raw_time
        print(
            f"\nPerformance: Raw={raw_time:.4f}s, Pydantic={pydantic_time:.4f}s, Ratio={overhead_ratio:.2f}x"
        )

        # Assertion: Overhead should be acceptable
        assert overhead_ratio < 10, f"Pydantic overhead too high: {overhead_ratio:.2f}x"

    def test_agent_result_serialization_performance(self):
        """Measure AgentResult serialization overhead."""
        iterations = 1000

        # Given: AgentResult instance
        agent_result = AgentResult(
            agent_name="test_agent",
            status="success",
            data={"results": list(range(10))},
            tokens_in=100,
            tokens_out=200,
            duration_ms=500,
        )

        # When: Serialize multiple times
        start = time.perf_counter()
        for _ in range(iterations):
            agent_result.model_dump()
        elapsed = time.perf_counter() - start

        # Then: Should complete quickly
        per_iteration_ms = (elapsed / iterations) * 1000
        print(f"\nAgentResult.model_dump() performance: {per_iteration_ms:.4f}ms per call")

        # Assertion: Should be fast (< 1ms per call)
        assert per_iteration_ms < 1.0, f"Serialization too slow: {per_iteration_ms:.4f}ms"


class TestErrorHandlingScenarios:
    """Test all error handling scenarios work correctly."""

    def test_partial_step_execution_with_error(self):
        """Test workflow when middle step fails."""
        # Given: 3 steps, 2nd fails
        step_results = [
            StepResult(
                step_index=0,
                tool_name="step1",
                args={},
                result={"success": True, "data": {"step1": "ok"}},
                success=True,
                error=None,
                error_code=None,
                execution_time_ms=100,
                hitl_approved=None,
            ),
            StepResult(
                step_index=1,
                tool_name="step2",
                args={},
                result={"success": False, "error": "TIMEOUT"},
                success=False,
                error="Operation timeout",
                error_code="TIMEOUT",
                execution_time_ms=5000,
                hitl_approved=None,
            ),
        ]

        execution_result = ExecutionResult(
            success=False,
            step_results=step_results,
            total_steps=3,
            completed_steps=1,  # Only 1 completed before failure
            failed_step_index=1,
            error="Step 1 failed: Operation timeout",
            error_code="TIMEOUT",
            total_execution_time_ms=5100,
            executed_at="2025-01-01T00:00:00Z",
        )

        # When: Mapper processes partial execution
        agent_results = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan_partial",
            turn_id=25,
        )

        # Then: AgentResult reflects partial completion
        result = agent_results[make_agent_result_key(25, "plan_executor")]
        assert result["status"] == "failed"
        assert result["error"] == "Step 1 failed: Operation timeout"
        assert result["data"]["completed_steps"] == 1
        assert result["data"]["total_steps"] == 3

        # And: Only successful step results are aggregated
        assert len(result["data"]["aggregated_results"]) == 1
        # The envelope is preserved, so the payload is under "data".
        assert result["data"]["aggregated_results"][0]["data"]["step1"] == "ok"

    def test_tool_response_with_empty_data(self):
        """Test ToolResponse handles empty data correctly."""
        # Given: Empty success response
        response = ToolResponse.success_response(data={})

        # When: Used in workflow
        step_result = StepResult(
            step_index=0,
            tool_name="empty_tool",
            args={},
            result=json.loads(response.model_dump_json()),
            success=True,
            error=None,
            error_code=None,
            execution_time_ms=10,
            hitl_approved=None,
        )

        # Then: Valid StepResult
        assert step_result.success is True
        assert step_result.result["success"] is True
        assert step_result.result["data"] == {}

    def test_contacts_result_data_with_zero_results(self):
        """Test ContactsResultData handles zero contacts correctly."""
        # Given: Zero contacts
        data = ContactsResultData(
            contacts=[],
            total_count=0,
            has_more=False,
            query="nonexistent",
        )

        # Then: Valid instance
        assert data.total_count == 0
        assert len(data.contacts) == 0
        assert data.has_more is False
        assert data.query == "nonexistent"


class TestJSONRoundTrips:
    """Test JSON serialization/deserialization preserves data."""

    def test_tool_response_json_round_trip(self):
        """Test ToolResponse survives JSON round trip."""
        # Given: ToolResponse
        original = ToolResponse.success_response(
            data={"contacts": [{"name": "Jean"}]},
            message="Found 1 contact",
            metadata={"turn_id": 5},
        )

        # When: Serialize and deserialize
        json_str = original.model_dump_json()
        restored = ToolResponse.model_validate_json(json_str)

        # Then: Data preserved
        assert restored.success == original.success
        assert restored.data == original.data
        assert restored.message == original.message
        assert restored.metadata == original.metadata

    def test_agent_result_with_contacts_data_round_trip(self):
        """Test AgentResult with ContactsResultData survives JSON round trip."""
        # Given: AgentResult with nested ContactsResultData
        original = AgentResult(
            agent_name="contacts_agent",
            status="success",
            data=ContactsResultData(contacts=[{"name": "Jean"}], total_count=1, query="Jean"),
            tokens_in=100,
            tokens_out=200,
            duration_ms=500,
        )

        # When: Serialize and deserialize
        json_str = original.model_dump_json()
        restored = AgentResult.model_validate_json(json_str)

        # Then: Pydantic smart deserialization reconstructs ContactsResultData
        assert restored.agent_name == original.agent_name
        assert restored.status == original.status
        assert isinstance(restored.data, ContactsResultData)
        assert restored.data.total_count == 1
        assert restored.data.query == "Jean"

    def test_execution_result_json_round_trip(self):
        """Test ExecutionResult survives JSON round trip."""
        # Given: ExecutionResult with StepResults
        original = ExecutionResult(
            success=True,
            step_results=[
                StepResult(
                    step_index=0,
                    tool_name="test_tool",
                    args={"query": "test"},
                    result={"success": True, "data": {"count": 5}},
                    success=True,
                    error=None,
                    error_code=None,
                    execution_time_ms=100,
                    hitl_approved=None,
                )
            ],
            total_steps=1,
            completed_steps=1,
            failed_step_index=None,
            error=None,
            error_code=None,
            total_execution_time_ms=100,
            executed_at="2025-01-01T00:00:00Z",
        )

        # When: Serialize and deserialize
        json_str = original.model_dump_json()
        restored = ExecutionResult.model_validate_json(json_str)

        # Then: All data preserved
        assert restored.success == original.success
        assert restored.total_steps == original.total_steps
        assert restored.completed_steps == original.completed_steps
        assert len(restored.step_results) == 1
        assert restored.step_results[0].tool_name == "test_tool"
        assert restored.step_results[0].result["data"]["count"] == 5


# ============================================================================
# E2E Tests for LLM Config Refactoring (Phase X)
# ============================================================================


class TestLLMConfigE2E:
    """E2E tests for LLM config refactoring."""

    @pytest.mark.e2e
    def test_router_llm_carries_no_static_metrics_callback(self):
        """The factory attaches NO static callback — that is the fix, not a gap.

        This test used to assert ``len(llm.callbacks) >= 1``, pinning the
        behaviour that caused **double token counting**: a static
        ``MetricsCallbackHandler`` on the instance PLUS the dynamic one added by
        ``enrich_config_with_node_metadata`` at invoke time. LangChain merges
        ``llm.callbacks`` with ``config["callbacks"]`` *after* the dynamic
        injector has filtered its own list, so both handlers ran and every call
        was counted twice. The factory now leaves the list empty on purpose
        (factory.py, "Metrics Double Counting Fix"); the handler is attached per
        invoke, which is also what gives it the node name for attribution.
        """
        from src.infrastructure.llm.factory import get_llm
        from src.infrastructure.observability.callbacks import MetricsCallbackHandler

        llm = get_llm("router")

        assert llm is not None
        assert llm.callbacks == [], (
            "a static callback on the instance is merged with the per-invoke one "
            "and doubles every token count"
        )
        assert not any(isinstance(cb, MetricsCallbackHandler) for cb in llm.callbacks or [])

    @pytest.mark.e2e
    def test_response_node_with_centralized_config(self):
        """
        Test response node uses centralized LLM config pattern.

        Scenario: Response node creates streaming LLM → uses centralized config.
        """
        from src.infrastructure.llm.factory import get_llm

        # When: Get response LLM (streaming enabled)
        llm = get_llm("response")

        # Then: LLM created with streaming
        assert llm is not None
        # Response LLM should have streaming enabled in factory

    @pytest.mark.e2e
    def test_planner_override_backward_compatibility(self):
        """
        Test planner config override backward compatibility.

        Scenario: Planner node uses TypedDict override → should still work
                  via backward compatibility layer.
        """
        from src.infrastructure.llm.factory import get_llm

        # When: Override with old TypedDict pattern (planner node does this)
        override_config = {
            "temperature": 0.0,  # Deterministic planning
            "max_tokens": 8000,
        }

        llm = get_llm("planner", config_override=override_config)

        # Then: LLM created successfully with overrides
        assert llm is not None

    @pytest.mark.e2e
    def test_new_pattern_llm_agent_config_override(self):
        """
        Test new LLMAgentConfig override pattern.

        Scenario: Use new Pydantic LLMAgentConfig for override → validates
                  and creates LLM correctly.
        """
        from src.core.llm_agent_config import LLMAgentConfig
        from src.infrastructure.llm.factory import get_llm

        # When: Use new pattern with LLMAgentConfig
        custom_config = LLMAgentConfig(
            provider="openai",
            model="gpt-4.1-mini-mini",
            temperature=0.8,
            top_p=0.95,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            max_tokens=10000,
        )

        llm = get_llm("contacts_agent", config_override=custom_config)

        # Then: LLM created with new pattern
        assert llm is not None
        assert hasattr(llm, "callbacks")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
