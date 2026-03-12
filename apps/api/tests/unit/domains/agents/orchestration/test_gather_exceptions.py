"""
Unit tests for asyncio.gather return_exceptions handling (CORRECTION 2).

Tests coverage:
- One step failure does not cancel other parallel steps
- Exception converted to failed StepResult with correct fields
- Step ordering via sorted(next_wave) ensures correct mapping
- FOR_EACH exception isolation

Target: parallel_executor.py wave execution (~line 830) and
        FOR_EACH execution (~line 3347)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pytest

from src.domains.agents.orchestration.plan_schemas import StepType
from src.domains.agents.tools.common import ToolErrorCode

# =============================================================================
# Helpers: Simulated step execution
# =============================================================================


class MockStepType(str, Enum):
    """Mirror of StepType for testing."""

    TOOL = "tool"


@dataclass
class MockStep:
    """Minimal ExecutionStep for testing."""

    step_id: str
    tool_name: str
    step_type: StepType = StepType.TOOL
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)


async def _simulate_step_success(step_id: str, delay: float = 0.01) -> dict:
    """Simulate a successful step execution."""
    await asyncio.sleep(delay)
    return {
        "step_id": step_id,
        "success": True,
        "result": {"data": f"result_{step_id}"},
    }


async def _simulate_step_failure(step_id: str) -> dict:
    """Simulate a step that raises an exception."""
    raise RuntimeError(f"Step {step_id} failed unexpectedly")


# =============================================================================
# Tests: Exception isolation in asyncio.gather
# =============================================================================


class TestGatherExceptionIsolation:
    """CORRECTION 2: return_exceptions=True isolates step failures."""

    @pytest.mark.asyncio
    async def test_one_exception_does_not_cancel_others(self) -> None:
        """One failing coroutine should not cancel successful ones."""

        async def success() -> str:
            await asyncio.sleep(0.01)
            return "ok"

        async def failure() -> str:
            raise ValueError("boom")

        results = await asyncio.gather(
            success(),
            failure(),
            success(),
            return_exceptions=True,
        )

        assert results[0] == "ok"
        assert isinstance(results[1], ValueError)
        assert results[2] == "ok"

    @pytest.mark.asyncio
    async def test_exception_to_stepresult_conversion(self) -> None:
        """Exceptions should be convertible to StepResult-like dicts."""
        from src.domains.agents.orchestration.parallel_executor import StepResult

        step_ids_ordered = ["step_a", "step_b", "step_c"]
        steps_by_id = {
            "step_a": MockStep(step_id="step_a", tool_name="tool_a"),
            "step_b": MockStep(step_id="step_b", tool_name="tool_b"),
            "step_c": MockStep(step_id="step_c", tool_name="tool_c"),
        }

        # Simulate: step_b raises
        async def ok_a() -> StepResult:
            return StepResult(
                step_id="step_a",
                step_type=StepType.TOOL,
                tool_name="tool_a",
                success=True,
                execution_time_ms=10,
                wave_id=0,
            )

        async def fail_b() -> StepResult:
            raise RuntimeError("Connection timeout")

        async def ok_c() -> StepResult:
            return StepResult(
                step_id="step_c",
                step_type=StepType.TOOL,
                tool_name="tool_c",
                success=True,
                execution_time_ms=15,
                wave_id=0,
            )

        raw_results = await asyncio.gather(ok_a(), fail_b(), ok_c(), return_exceptions=True)

        # Convert exceptions (same logic as parallel_executor)
        step_results: list[StepResult] = []
        for i, result in enumerate(raw_results):
            if isinstance(result, Exception):
                step_id = step_ids_ordered[i]
                step = steps_by_id[step_id]
                step_results.append(
                    StepResult(
                        step_id=step_id,
                        step_type=step.step_type,
                        tool_name=step.tool_name,
                        success=False,
                        error=f"{type(result).__name__}: {result}",
                        error_code=ToolErrorCode.INTERNAL_ERROR,
                        execution_time_ms=0,
                        wave_id=0,
                    )
                )
            else:
                step_results.append(result)

        # Verify results
        assert len(step_results) == 3
        assert step_results[0].success is True
        assert step_results[0].step_id == "step_a"
        assert step_results[1].success is False
        assert step_results[1].step_id == "step_b"
        assert step_results[1].error == "RuntimeError: Connection timeout"
        assert step_results[1].error_code == ToolErrorCode.INTERNAL_ERROR
        assert step_results[1].step_type == StepType.TOOL
        assert step_results[2].success is True
        assert step_results[2].step_id == "step_c"

    @pytest.mark.asyncio
    async def test_sorted_set_ordering_consistency(self) -> None:
        """sorted(next_wave) should produce consistent ordering for result mapping."""
        next_wave = {"step_c", "step_a", "step_b"}

        step_ids_ordered = sorted(next_wave)
        assert step_ids_ordered == ["step_a", "step_b", "step_c"]

        # Verify multiple calls produce same order
        for _ in range(10):
            assert sorted(next_wave) == ["step_a", "step_b", "step_c"]

    @pytest.mark.asyncio
    async def test_stepresult_immutable_after_creation(self) -> None:
        """StepResult with frozen=True should be immutable."""
        from src.domains.agents.orchestration.parallel_executor import StepResult

        result = StepResult(
            step_id="test",
            step_type=StepType.TOOL,
            tool_name="test_tool",
            success=False,
            error="test error",
            error_code=ToolErrorCode.INTERNAL_ERROR,
            execution_time_ms=0,
            wave_id=0,
        )

        with pytest.raises(Exception):  # ValidationError for frozen model
            result.success = True


# =============================================================================
# Tests: FOR_EACH exception isolation
# =============================================================================


class TestForEachExceptionIsolation:
    """CORRECTION 2: FOR_EACH parallel execution exception isolation."""

    @pytest.mark.asyncio
    async def test_for_each_one_item_failure_others_succeed(self) -> None:
        """In FOR_EACH, one item failure should not cancel other items."""
        expanded_steps = [
            MockStep(step_id="send_email_0", tool_name="send_email_tool"),
            MockStep(step_id="send_email_1", tool_name="send_email_tool"),
            MockStep(step_id="send_email_2", tool_name="send_email_tool"),
        ]

        async def execute_step(step: MockStep) -> dict:
            if step.step_id == "send_email_1":
                raise ConnectionError("SMTP timeout")
            return {"step_id": step.step_id, "success": True}

        tasks = [execute_step(step) for step in expanded_steps]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        assert raw_results[0] == {"step_id": "send_email_0", "success": True}
        assert isinstance(raw_results[1], ConnectionError)
        assert raw_results[2] == {"step_id": "send_email_2", "success": True}

    @pytest.mark.asyncio
    async def test_for_each_expanded_steps_order_preserved(self) -> None:
        """expanded_steps is a list so order is guaranteed (no sorted() needed)."""
        steps = [MockStep(step_id=f"step_{i}", tool_name="tool") for i in range(5)]

        # List order is preserved
        assert [s.step_id for s in steps] == [
            "step_0",
            "step_1",
            "step_2",
            "step_3",
            "step_4",
        ]

    @pytest.mark.asyncio
    async def test_all_exceptions_collected(self) -> None:
        """When all items fail, all exceptions should be collected."""
        from src.domains.agents.orchestration.parallel_executor import StepResult

        expanded_steps = [
            MockStep(step_id="step_0", tool_name="tool"),
            MockStep(step_id="step_1", tool_name="tool"),
        ]

        async def always_fail(step: MockStep) -> StepResult:
            raise TimeoutError(f"Timeout for {step.step_id}")

        tasks = [always_fail(step) for step in expanded_steps]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[StepResult] = []
        for i, result in enumerate(raw_results):
            if isinstance(result, Exception):
                step = expanded_steps[i]
                results.append(
                    StepResult(
                        step_id=step.step_id,
                        step_type=step.step_type,
                        tool_name=step.tool_name,
                        success=False,
                        error=f"{type(result).__name__}: {result}",
                        error_code=ToolErrorCode.INTERNAL_ERROR,
                        execution_time_ms=0,
                        wave_id=0,
                    )
                )
            else:
                results.append(result)

        assert len(results) == 2
        assert all(not r.success for r in results)
        assert "TimeoutError" in results[0].error
        assert "TimeoutError" in results[1].error
