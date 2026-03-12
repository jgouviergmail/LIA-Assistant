"""
Tests for for_each execution with delay and error handling.

This module tests the _execute_for_each_wave function in parallel_executor.py
which handles:
1. delay_between_items_ms - sequential execution with throttling
2. on_item_error - error handling strategies (continue/stop/collect_errors)
"""

import asyncio
from unittest.mock import patch

import pytest

from src.domains.agents.orchestration.parallel_executor import (
    StepResult,
    _execute_for_each_wave,
)
from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType
from src.domains.agents.tools.common import ToolErrorCode

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def original_for_each_step():
    """Original for_each step with config."""
    return ExecutionStep(
        step_id="send_emails",
        step_type=StepType.TOOL,
        agent_name="email_agent",
        tool_name="send_email_tool",
        parameters={"to": "$item.email", "subject": "Test"},
        for_each="$steps.get_contacts.contacts",
        for_each_max=10,
        delay_between_items_ms=0,
        on_item_error="continue",
    )


@pytest.fixture
def expanded_steps():
    """Expanded steps from for_each."""
    return [
        ExecutionStep(
            step_id="send_emails_item_0",
            step_type=StepType.TOOL,
            agent_name="email_agent",
            tool_name="send_email_tool",
            parameters={"to": "alice@example.com", "subject": "Test"},
        ),
        ExecutionStep(
            step_id="send_emails_item_1",
            step_type=StepType.TOOL,
            agent_name="email_agent",
            tool_name="send_email_tool",
            parameters={"to": "bob@example.com", "subject": "Test"},
        ),
        ExecutionStep(
            step_id="send_emails_item_2",
            step_type=StepType.TOOL,
            agent_name="email_agent",
            tool_name="send_email_tool",
            parameters={"to": "charlie@example.com", "subject": "Test"},
        ),
    ]


@pytest.fixture
def mock_config():
    """Mock RunnableConfig."""
    return {"configurable": {"user_id": "test_user", "thread_id": "test_thread"}}


def create_step_result(step_id: str, success: bool = True, error: str | None = None) -> StepResult:
    """Helper to create StepResult objects."""
    return StepResult(
        step_id=step_id,
        step_type=StepType.TOOL,
        tool_name="send_email_tool",
        args={"to": "test@example.com"},
        result={"status": "ok"} if success else None,
        success=success,
        error=error,
        error_code=ToolErrorCode.INTERNAL_ERROR if error else None,
        execution_time_ms=100,
        wave_id=0,
        registry_updates=None,
        draft_info=None,
    )


# ============================================================================
# Tests: Parallel Execution (delay_between_items_ms = 0)
# ============================================================================


class TestForEachParallelExecution:
    """Tests for parallel execution when delay_between_items_ms = 0."""

    @pytest.mark.asyncio
    async def test_parallel_execution_no_delay(
        self, original_for_each_step, expanded_steps, mock_config
    ):
        """When delay_between_items_ms=0, all steps execute in parallel."""
        original_for_each_step.delay_between_items_ms = 0

        execution_times = []

        async def mock_execute_step(**kwargs):
            execution_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.01)  # Simulate some work
            return create_step_result(kwargs["step"].step_id)

        with patch(
            "src.domains.agents.orchestration.parallel_executor._execute_single_step_async",
            side_effect=mock_execute_step,
        ):
            results, errors = await _execute_for_each_wave(
                expanded_steps=expanded_steps,
                original_step=original_for_each_step,
                completed_steps={},
                config=mock_config,
                store=None,
                context={},
                wave_id=0,
                run_id="test_run",
            )

        # All 3 steps should complete
        assert len(results) == 3
        assert all(r.success for r in results)
        assert len(errors) == 0

        # Execution times should be very close (parallel)
        # The difference between first and last should be < 0.05s
        time_span = max(execution_times) - min(execution_times)
        assert time_span < 0.05, f"Steps did not execute in parallel: time span = {time_span}s"


# ============================================================================
# Tests: Sequential Execution (delay_between_items_ms > 0)
# ============================================================================


class TestForEachSequentialExecution:
    """Tests for sequential execution when delay_between_items_ms > 0."""

    @pytest.mark.asyncio
    async def test_sequential_execution_with_delay(
        self, original_for_each_step, expanded_steps, mock_config
    ):
        """When delay_between_items_ms>0, steps execute sequentially with delay."""
        original_for_each_step.delay_between_items_ms = 100  # 100ms delay

        execution_times = []

        async def mock_execute_step(**kwargs):
            execution_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.01)  # Simulate some work
            return create_step_result(kwargs["step"].step_id)

        with patch(
            "src.domains.agents.orchestration.parallel_executor._execute_single_step_async",
            side_effect=mock_execute_step,
        ):
            results, errors = await _execute_for_each_wave(
                expanded_steps=expanded_steps,
                original_step=original_for_each_step,
                completed_steps={},
                config=mock_config,
                store=None,
                context={},
                wave_id=0,
                run_id="test_run",
            )

        # All 3 steps should complete
        assert len(results) == 3
        assert all(r.success for r in results)
        assert len(errors) == 0

        # Execution times should be at least 100ms apart (sequential with delay)
        # With 3 items and 100ms delay, total time should be ~200ms+ (2 delays)
        if len(execution_times) >= 2:
            # Check that there's a delay between consecutive executions
            for i in range(1, len(execution_times)):
                gap = execution_times[i] - execution_times[i - 1]
                # Gap should be at least 90ms (allowing some tolerance)
                assert gap >= 0.09, f"Gap between step {i-1} and {i} was only {gap}s"


# ============================================================================
# Tests: Error Handling (on_item_error)
# ============================================================================


class TestForEachErrorHandling:
    """Tests for on_item_error handling."""

    @pytest.mark.asyncio
    async def test_on_item_error_continue(
        self, original_for_each_step, expanded_steps, mock_config
    ):
        """With on_item_error='continue', execution continues after failures."""
        original_for_each_step.delay_between_items_ms = 50  # Sequential for predictable order
        original_for_each_step.on_item_error = "continue"

        call_count = 0

        async def mock_execute_step(**kwargs):
            nonlocal call_count
            call_count += 1
            step_id = kwargs["step"].step_id

            # Second step fails
            if "item_1" in step_id:
                return create_step_result(step_id, success=False, error="Test error")
            return create_step_result(step_id)

        with patch(
            "src.domains.agents.orchestration.parallel_executor._execute_single_step_async",
            side_effect=mock_execute_step,
        ):
            results, errors = await _execute_for_each_wave(
                expanded_steps=expanded_steps,
                original_step=original_for_each_step,
                completed_steps={},
                config=mock_config,
                store=None,
                context={},
                wave_id=0,
                run_id="test_run",
            )

        # All 3 steps should have executed
        assert call_count == 3
        assert len(results) == 3

        # Check results
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

        # 1 error should be collected
        assert len(errors) == 1
        assert errors[0]["step_id"] == "send_emails_item_1"

    @pytest.mark.asyncio
    async def test_on_item_error_stop(self, original_for_each_step, expanded_steps, mock_config):
        """With on_item_error='stop', execution stops on first failure."""
        original_for_each_step.delay_between_items_ms = 50  # Sequential for predictable order
        original_for_each_step.on_item_error = "stop"

        call_count = 0

        async def mock_execute_step(**kwargs):
            nonlocal call_count
            call_count += 1
            step_id = kwargs["step"].step_id

            # Second step fails
            if "item_1" in step_id:
                return create_step_result(step_id, success=False, error="Test error")
            return create_step_result(step_id)

        with patch(
            "src.domains.agents.orchestration.parallel_executor._execute_single_step_async",
            side_effect=mock_execute_step,
        ):
            results, errors = await _execute_for_each_wave(
                expanded_steps=expanded_steps,
                original_step=original_for_each_step,
                completed_steps={},
                config=mock_config,
                store=None,
                context={},
                wave_id=0,
                run_id="test_run",
            )

        # Only 2 steps should have executed (stopped on error)
        assert call_count == 2
        assert len(results) == 2

        # Check results
        assert results[0].success is True
        assert results[1].success is False

        # 1 error should be collected
        assert len(errors) == 1
        assert errors[0]["step_id"] == "send_emails_item_1"

    @pytest.mark.asyncio
    async def test_on_item_error_collect_errors(
        self, original_for_each_step, expanded_steps, mock_config
    ):
        """With on_item_error='collect_errors', all errors are collected."""
        original_for_each_step.delay_between_items_ms = 50
        original_for_each_step.on_item_error = "collect_errors"

        call_count = 0

        async def mock_execute_step(**kwargs):
            nonlocal call_count
            call_count += 1
            step_id = kwargs["step"].step_id

            # First and second steps fail
            if "item_0" in step_id or "item_1" in step_id:
                return create_step_result(step_id, success=False, error=f"Error for {step_id}")
            return create_step_result(step_id)

        with patch(
            "src.domains.agents.orchestration.parallel_executor._execute_single_step_async",
            side_effect=mock_execute_step,
        ):
            results, errors = await _execute_for_each_wave(
                expanded_steps=expanded_steps,
                original_step=original_for_each_step,
                completed_steps={},
                config=mock_config,
                store=None,
                context={},
                wave_id=0,
                run_id="test_run",
            )

        # All 3 steps should have executed
        assert call_count == 3
        assert len(results) == 3

        # Check results
        assert results[0].success is False
        assert results[1].success is False
        assert results[2].success is True

        # 2 errors should be collected
        assert len(errors) == 2
        assert errors[0]["step_id"] == "send_emails_item_0"
        assert errors[1]["step_id"] == "send_emails_item_1"


# ============================================================================
# Tests: Edge Cases
# ============================================================================


class TestForEachEdgeCases:
    """Tests for edge cases in for_each execution."""

    @pytest.mark.asyncio
    async def test_empty_expanded_steps(self, original_for_each_step, mock_config):
        """Handle empty expanded_steps list gracefully."""
        results, errors = await _execute_for_each_wave(
            expanded_steps=[],  # Empty list
            original_step=original_for_each_step,
            completed_steps={},
            config=mock_config,
            store=None,
            context={},
            wave_id=0,
            run_id="test_run",
        )

        assert len(results) == 0
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_single_expanded_step(self, original_for_each_step, mock_config):
        """Handle single expanded step (no delay between items needed)."""
        original_for_each_step.delay_between_items_ms = 100

        single_step = ExecutionStep(
            step_id="send_emails_item_0",
            step_type=StepType.TOOL,
            agent_name="email_agent",
            tool_name="send_email_tool",
            parameters={"to": "alice@example.com"},
        )

        async def mock_execute_step(**kwargs):
            return create_step_result(kwargs["step"].step_id)

        with patch(
            "src.domains.agents.orchestration.parallel_executor._execute_single_step_async",
            side_effect=mock_execute_step,
        ):
            results, errors = await _execute_for_each_wave(
                expanded_steps=[single_step],
                original_step=original_for_each_step,
                completed_steps={},
                config=mock_config,
                store=None,
                context={},
                wave_id=0,
                run_id="test_run",
            )

        assert len(results) == 1
        assert results[0].success is True
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_all_steps_fail_with_collect_errors(
        self, original_for_each_step, expanded_steps, mock_config
    ):
        """All steps failing should collect all errors."""
        original_for_each_step.delay_between_items_ms = 50
        original_for_each_step.on_item_error = "collect_errors"

        async def mock_execute_step(**kwargs):
            step_id = kwargs["step"].step_id
            return create_step_result(step_id, success=False, error="All fail")

        with patch(
            "src.domains.agents.orchestration.parallel_executor._execute_single_step_async",
            side_effect=mock_execute_step,
        ):
            results, errors = await _execute_for_each_wave(
                expanded_steps=expanded_steps,
                original_step=original_for_each_step,
                completed_steps={},
                config=mock_config,
                store=None,
                context={},
                wave_id=0,
                run_id="test_run",
            )

        assert len(results) == 3
        assert all(not r.success for r in results)
        assert len(errors) == 3


# ============================================================================
# FOR_EACH Result Aggregation Tests
# ============================================================================


class TestForEachResultAggregation:
    """Tests for _aggregate_for_each_results function."""

    def test_aggregate_list_values(self):
        """Lists from expanded steps should be concatenated."""
        from src.domains.agents.orchestration.parallel_executor import (
            _aggregate_for_each_results,
        )

        completed_steps = {
            "step_2_item_0": {"places": ["restaurant_a", "restaurant_b"]},
            "step_2_item_1": {"places": ["restaurant_c", "restaurant_d"]},
        }

        _aggregate_for_each_results(
            completed_steps=completed_steps,
            original_step_id="step_2",
            expanded_step_ids=["step_2_item_0", "step_2_item_1"],
        )

        assert "step_2" in completed_steps
        assert completed_steps["step_2"]["places"] == [
            "restaurant_a",
            "restaurant_b",
            "restaurant_c",
            "restaurant_d",
        ]

    def test_aggregate_non_list_values_uses_last(self):
        """Non-list values should use the last non-None value."""
        from src.domains.agents.orchestration.parallel_executor import (
            _aggregate_for_each_results,
        )

        completed_steps = {
            "step_2_item_0": {"count": 2, "status": "success"},
            "step_2_item_1": {"count": 3, "status": "partial"},
        }

        _aggregate_for_each_results(
            completed_steps=completed_steps,
            original_step_id="step_2",
            expanded_step_ids=["step_2_item_0", "step_2_item_1"],
        )

        assert completed_steps["step_2"]["count"] == 3  # Last value
        assert completed_steps["step_2"]["status"] == "partial"  # Last value

    def test_aggregate_mixed_values(self):
        """Mix of lists and non-lists should be handled correctly."""
        from src.domains.agents.orchestration.parallel_executor import (
            _aggregate_for_each_results,
        )

        completed_steps = {
            "step_2_item_0": {"places": ["a", "b"], "message": "Found 2"},
            "step_2_item_1": {"places": ["c"], "message": "Found 1"},
        }

        _aggregate_for_each_results(
            completed_steps=completed_steps,
            original_step_id="step_2",
            expanded_step_ids=["step_2_item_0", "step_2_item_1"],
        )

        assert completed_steps["step_2"]["places"] == ["a", "b", "c"]
        assert completed_steps["step_2"]["message"] == "Found 1"  # Last value

    def test_aggregate_empty_expanded_steps(self):
        """Empty expanded_step_ids should not create aggregated entry."""
        from src.domains.agents.orchestration.parallel_executor import (
            _aggregate_for_each_results,
        )

        completed_steps = {}

        _aggregate_for_each_results(
            completed_steps=completed_steps,
            original_step_id="step_2",
            expanded_step_ids=[],
        )

        assert "step_2" not in completed_steps

    def test_aggregate_missing_expanded_results(self):
        """Missing expanded step results should be handled gracefully."""
        from src.domains.agents.orchestration.parallel_executor import (
            _aggregate_for_each_results,
        )

        completed_steps = {
            "step_2_item_0": {"places": ["a", "b"]},
            # step_2_item_1 is missing from completed_steps
        }

        _aggregate_for_each_results(
            completed_steps=completed_steps,
            original_step_id="step_2",
            expanded_step_ids=["step_2_item_0", "step_2_item_1"],
        )

        # Should aggregate only available results
        assert "step_2" in completed_steps
        assert completed_steps["step_2"]["places"] == ["a", "b"]

    def test_aggregate_all_missing_results(self):
        """All missing expanded results should not crash."""
        from src.domains.agents.orchestration.parallel_executor import (
            _aggregate_for_each_results,
        )

        completed_steps = {}

        _aggregate_for_each_results(
            completed_steps=completed_steps,
            original_step_id="step_2",
            expanded_step_ids=["step_2_item_0", "step_2_item_1"],
        )

        # Should not create entry if no results found
        assert "step_2" not in completed_steps

    def test_aggregate_result_strings_into_list(self):
        """BugFix 2026-01-22: String 'result' values should be collected into a list."""
        from src.domains.agents.orchestration.parallel_executor import (
            _aggregate_for_each_results,
        )

        # Simulating FOR_EACH reminders: each step returns a confirmation message
        completed_steps = {
            "step_2_item_0": {"result": "🔔 Rappel créé pour mardi 27 janvier 2026 à 11:30"},
            "step_2_item_1": {"result": "🔔 Rappel créé pour samedi 31 janvier 2026 à 12:00"},
        }

        _aggregate_for_each_results(
            completed_steps=completed_steps,
            original_step_id="step_2",
            expanded_step_ids=["step_2_item_0", "step_2_item_1"],
        )

        # 'result' should now be a list of all messages (not just the last one)
        assert "step_2" in completed_steps
        assert isinstance(completed_steps["step_2"]["result"], list)
        assert len(completed_steps["step_2"]["result"]) == 2
        assert "27 janvier" in completed_steps["step_2"]["result"][0]
        assert "31 janvier" in completed_steps["step_2"]["result"][1]

    def test_aggregate_single_result_stays_string(self):
        """Single 'result' value should remain a string (backward compatibility)."""
        from src.domains.agents.orchestration.parallel_executor import (
            _aggregate_for_each_results,
        )

        completed_steps = {
            "step_2_item_0": {"result": "🔔 Rappel créé pour mardi 27 janvier 2026 à 11:30"},
        }

        _aggregate_for_each_results(
            completed_steps=completed_steps,
            original_step_id="step_2",
            expanded_step_ids=["step_2_item_0"],
        )

        # Single result should stay as string
        assert (
            completed_steps["step_2"]["result"]
            == "🔔 Rappel créé pour mardi 27 janvier 2026 à 11:30"
        )


# ============================================================================
# Action Success Messages Extraction Tests (BugFix 2026-01-22)
# ============================================================================


class TestExtractActionSuccessMessages:
    """Tests for _extract_action_success_messages function."""

    def test_extract_single_result_string(self):
        """Extract single string result message."""
        from src.domains.agents.formatters.agent_results import (
            _extract_action_success_messages,
        )

        data = {
            "aggregated_results": [{"result": "🔔 Rappel créé pour mardi 27 janvier 2026 à 11:30"}]
        }

        messages = _extract_action_success_messages(data)

        assert len(messages) == 1
        assert "27 janvier" in messages[0]

    def test_extract_result_list_from_for_each(self):
        """BugFix 2026-01-22: Extract list of result messages from FOR_EACH aggregation."""
        from src.domains.agents.formatters.agent_results import (
            _extract_action_success_messages,
        )

        data = {
            "aggregated_results": [
                {
                    "result": [
                        "🔔 Rappel créé pour mardi 27 janvier 2026 à 11:30",
                        "🔔 Rappel créé pour samedi 31 janvier 2026 à 12:00",
                    ]
                }
            ]
        }

        messages = _extract_action_success_messages(data)

        assert len(messages) == 2
        assert "27 janvier" in messages[0]
        assert "31 janvier" in messages[1]

    def test_extract_mixed_results(self):
        """Extract from multiple step results with mixed formats."""
        from src.domains.agents.formatters.agent_results import (
            _extract_action_success_messages,
        )

        data = {
            "step_results": [
                {"events": [{"id": "evt1"}]},  # Calendar search (no result key)
                {
                    "result": [
                        "🔔 Rappel 1",
                        "🔔 Rappel 2",
                    ]
                },  # FOR_EACH reminders
            ]
        }

        messages = _extract_action_success_messages(data)

        assert len(messages) == 2
        assert "Rappel 1" in messages[0]
        assert "Rappel 2" in messages[1]

    def test_extract_avoids_duplicates(self):
        """Duplicate messages should be filtered out."""
        from src.domains.agents.formatters.agent_results import (
            _extract_action_success_messages,
        )

        data = {
            "step_results": [{"result": "🔔 Same message"}],
            "aggregated_results": [{"result": "🔔 Same message"}],  # Duplicate
        }

        messages = _extract_action_success_messages(data)

        assert len(messages) == 1
        assert messages[0] == "🔔 Same message"
