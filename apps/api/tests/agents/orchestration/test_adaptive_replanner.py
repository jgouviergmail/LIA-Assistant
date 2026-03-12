"""
INTELLIPLANNER Phase E - Tests for AdaptiveRePlanner.

Validates:
1. Trigger detection (empty results, partial failure, etc.)
2. Decision making (proceed, retry, abort, etc.)
3. Recovery strategy selection
4. Max attempts enforcement
5. Analysis accuracy

Created: 2025-12-03
"""

import pytest

from src.domains.agents.orchestration.adaptive_replanner import (
    AdaptiveRePlanner,
    ExecutionAnalysis,
    RecoveryStrategy,
    RePlanContext,
    RePlanDecision,
    RePlanResult,
    RePlanTrigger,
    StepAnalysis,
    analyze_execution_results,
    should_trigger_replan,
)
from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_execution_plan() -> ExecutionPlan:
    """Create a sample execution plan for testing."""
    return ExecutionPlan(
        plan_id="test_plan_001",
        user_id="test_user_001",  # Required field
        execution_mode="parallel",
        steps=[
            ExecutionStep(
                step_id="search_contacts",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",
                tool_name="search_contacts_tool",
                parameters={"query": "John"},
                description="Search for contacts named John",
            ),
            ExecutionStep(
                step_id="get_details",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",
                tool_name="get_contact_details_tool",
                parameters={"contact_id": "{{ steps.search_contacts.contacts[0].id }}"},
                description="Get details of first contact",
                depends_on=["search_contacts"],
            ),
        ],
        estimated_cost_usd=0.001,
    )


@pytest.fixture
def successful_completed_steps() -> dict:
    """Completed steps with successful results."""
    return {
        "search_contacts": {
            "success": True,
            "contacts": [{"id": "c1", "name": "John Doe"}, {"id": "c2", "name": "John Smith"}],
            "count": 2,
        },
        "get_details": {
            "success": True,
            "contacts": [{"id": "c1", "name": "John Doe", "email": "john@example.com"}],
            "count": 1,
        },
    }


@pytest.fixture
def empty_completed_steps() -> dict:
    """Completed steps with empty results."""
    return {
        "search_contacts": {
            "success": True,
            "contacts": [],
            "count": 0,
        },
        "get_details": {
            "success": True,
            "contacts": [],
            "count": 0,
        },
    }


@pytest.fixture
def partial_failure_steps() -> dict:
    """Completed steps with some failures."""
    return {
        "search_contacts": {
            "success": True,
            "contacts": [{"id": "c1", "name": "John"}],
            "count": 1,
        },
        "get_details": {
            "success": False,
            "error": "Contact not found",
        },
    }


# ============================================================================
# Test: Execution Analysis
# ============================================================================


class TestExecutionAnalysis:
    """Tests for analyze_execution_results function."""

    def test_analyze_successful_execution(
        self, sample_execution_plan: ExecutionPlan, successful_completed_steps: dict
    ):
        """Successful execution is analyzed correctly."""
        analysis = analyze_execution_results(
            execution_plan=sample_execution_plan,
            completed_steps=successful_completed_steps,
        )

        assert analysis.total_steps == 2
        assert analysis.completed_steps == 2
        assert analysis.successful_steps == 2
        assert analysis.failed_steps == 0
        assert analysis.empty_steps == 0
        assert analysis.total_results == 3  # 2 + 1
        assert analysis.success_rate == 1.0
        assert not analysis.is_complete_failure
        assert not analysis.is_partial_failure
        assert not analysis.is_all_empty

    def test_analyze_empty_results(
        self, sample_execution_plan: ExecutionPlan, empty_completed_steps: dict
    ):
        """Empty results are detected correctly."""
        analysis = analyze_execution_results(
            execution_plan=sample_execution_plan,
            completed_steps=empty_completed_steps,
        )

        assert analysis.successful_steps == 2
        assert analysis.empty_steps == 2
        assert analysis.total_results == 0
        assert analysis.is_all_empty
        assert analysis.empty_rate == 1.0

    def test_analyze_partial_failure(
        self, sample_execution_plan: ExecutionPlan, partial_failure_steps: dict
    ):
        """Partial failures are detected correctly."""
        analysis = analyze_execution_results(
            execution_plan=sample_execution_plan,
            completed_steps=partial_failure_steps,
        )

        assert analysis.successful_steps == 1
        assert analysis.failed_steps == 1
        assert analysis.is_partial_failure
        assert analysis.success_rate == 0.5


# ============================================================================
# Test: Trigger Detection
# ============================================================================


class TestTriggerDetection:
    """Tests for should_trigger_replan function."""

    def test_no_trigger_for_successful_execution(
        self, sample_execution_plan: ExecutionPlan, successful_completed_steps: dict
    ):
        """Successful execution does not trigger re-planning."""
        should_replan, trigger = should_trigger_replan(
            execution_plan=sample_execution_plan,
            completed_steps=successful_completed_steps,
        )

        assert not should_replan
        assert trigger == RePlanTrigger.NONE

    def test_trigger_for_empty_results(
        self, sample_execution_plan: ExecutionPlan, empty_completed_steps: dict
    ):
        """Empty results trigger re-planning."""
        should_replan, trigger = should_trigger_replan(
            execution_plan=sample_execution_plan,
            completed_steps=empty_completed_steps,
        )

        assert should_replan
        assert trigger == RePlanTrigger.EMPTY_RESULTS

    def test_trigger_for_partial_failure(
        self, sample_execution_plan: ExecutionPlan, partial_failure_steps: dict
    ):
        """Partial failure triggers re-planning."""
        should_replan, trigger = should_trigger_replan(
            execution_plan=sample_execution_plan,
            completed_steps=partial_failure_steps,
        )

        assert should_replan
        assert trigger == RePlanTrigger.PARTIAL_FAILURE

    def test_trigger_for_complete_failure(self, sample_execution_plan: ExecutionPlan):
        """Complete failure triggers re-planning."""
        all_failed_steps = {
            "search_contacts": {"success": False, "error": "API error"},
            "get_details": {"success": False, "error": "API error"},
        }

        should_replan, trigger = should_trigger_replan(
            execution_plan=sample_execution_plan,
            completed_steps=all_failed_steps,
        )

        assert should_replan
        assert trigger == RePlanTrigger.PARTIAL_FAILURE


# ============================================================================
# Test: AdaptiveRePlanner Decisions
# ============================================================================


class TestAdaptiveReplannerDecisions:
    """Tests for AdaptiveRePlanner decision making."""

    def test_proceed_on_successful_execution(
        self, sample_execution_plan: ExecutionPlan, successful_completed_steps: dict
    ):
        """Successful execution results in PROCEED decision."""
        replanner = AdaptiveRePlanner()
        analysis = analyze_execution_results(sample_execution_plan, successful_completed_steps)

        context = RePlanContext(
            user_request="Find John",
            user_language="en",
            execution_plan=sample_execution_plan,
            plan_id=sample_execution_plan.plan_id,
            completed_steps=successful_completed_steps,
            execution_analysis=analysis,
            replan_attempt=0,
            max_attempts=3,
        )

        result = replanner.analyze_and_decide(context)

        assert result.decision == RePlanDecision.PROCEED
        assert result.trigger == RePlanTrigger.NONE

    def test_replan_on_empty_results_first_attempt(
        self, sample_execution_plan: ExecutionPlan, empty_completed_steps: dict
    ):
        """Empty results on first attempt triggers REPLAN_MODIFIED with BROADEN_SEARCH."""
        replanner = AdaptiveRePlanner()
        analysis = analyze_execution_results(sample_execution_plan, empty_completed_steps)

        context = RePlanContext(
            user_request="Find John",
            user_language="en",
            execution_plan=sample_execution_plan,
            plan_id=sample_execution_plan.plan_id,
            completed_steps=empty_completed_steps,
            execution_analysis=analysis,
            replan_attempt=0,
            max_attempts=3,
        )

        result = replanner.analyze_and_decide(context)

        assert result.decision == RePlanDecision.REPLAN_MODIFIED
        assert result.trigger == RePlanTrigger.EMPTY_RESULTS
        assert result.recovery_strategy == RecoveryStrategy.BROADEN_SEARCH

    def test_escalate_on_empty_results_third_attempt(
        self, sample_execution_plan: ExecutionPlan, empty_completed_steps: dict
    ):
        """Empty results on third attempt triggers ESCALATE_USER."""
        replanner = AdaptiveRePlanner()
        analysis = analyze_execution_results(sample_execution_plan, empty_completed_steps)

        context = RePlanContext(
            user_request="Find John",
            user_language="en",
            execution_plan=sample_execution_plan,
            plan_id=sample_execution_plan.plan_id,
            completed_steps=empty_completed_steps,
            execution_analysis=analysis,
            replan_attempt=2,  # Third attempt (0-indexed)
            max_attempts=3,
        )

        result = replanner.analyze_and_decide(context)

        assert result.decision == RePlanDecision.ESCALATE_USER
        assert result.user_message is not None

    def test_abort_on_max_attempts_exceeded(
        self, sample_execution_plan: ExecutionPlan, empty_completed_steps: dict
    ):
        """Exceeding max attempts triggers ABORT."""
        replanner = AdaptiveRePlanner()
        analysis = analyze_execution_results(sample_execution_plan, empty_completed_steps)

        context = RePlanContext(
            user_request="Find John",
            user_language="en",
            execution_plan=sample_execution_plan,
            plan_id=sample_execution_plan.plan_id,
            completed_steps=empty_completed_steps,
            execution_analysis=analysis,
            replan_attempt=3,  # At max
            max_attempts=3,
        )

        result = replanner.analyze_and_decide(context)

        assert result.decision == RePlanDecision.ABORT
        assert result.user_message is not None

    def test_retry_same_on_partial_failure_first_attempt(
        self, sample_execution_plan: ExecutionPlan, partial_failure_steps: dict
    ):
        """Partial failure on first attempt triggers RETRY_SAME (transient)."""
        replanner = AdaptiveRePlanner()
        analysis = analyze_execution_results(sample_execution_plan, partial_failure_steps)

        context = RePlanContext(
            user_request="Find John",
            user_language="en",
            execution_plan=sample_execution_plan,
            plan_id=sample_execution_plan.plan_id,
            completed_steps=partial_failure_steps,
            execution_analysis=analysis,
            replan_attempt=0,
            max_attempts=3,
        )

        result = replanner.analyze_and_decide(context)

        assert result.decision == RePlanDecision.RETRY_SAME
        assert result.trigger == RePlanTrigger.PARTIAL_FAILURE


# ============================================================================
# Test: StepAnalysis Properties
# ============================================================================


class TestStepAnalysisProperties:
    """Tests for StepAnalysis dataclass properties."""

    def test_is_empty_when_success_but_no_results(self):
        """is_empty is True when step succeeded but has no results."""
        analysis = StepAnalysis(
            step_id="test",
            tool_name="test_tool",
            success=True,
            has_results=False,
            result_count=0,
            error=None,
            execution_time_ms=100,
        )

        assert analysis.is_empty

    def test_is_not_empty_when_has_results(self):
        """is_empty is False when step has results."""
        analysis = StepAnalysis(
            step_id="test",
            tool_name="test_tool",
            success=True,
            has_results=True,
            result_count=5,
            error=None,
            execution_time_ms=100,
        )

        assert not analysis.is_empty

    def test_is_not_empty_when_failed(self):
        """is_empty is False when step failed (even if no results)."""
        analysis = StepAnalysis(
            step_id="test",
            tool_name="test_tool",
            success=False,
            has_results=False,
            result_count=0,
            error="Error occurred",
            execution_time_ms=100,
        )

        assert not analysis.is_empty


# ============================================================================
# Test: ExecutionAnalysis Properties
# ============================================================================


class TestExecutionAnalysisProperties:
    """Tests for ExecutionAnalysis dataclass properties."""

    def test_success_rate_calculation(self):
        """success_rate is calculated correctly."""
        analysis = ExecutionAnalysis(
            total_steps=4,
            completed_steps=4,
            successful_steps=3,
            failed_steps=1,
            empty_steps=0,
            total_results=10,
            execution_time_ms=500,
        )

        assert analysis.success_rate == 0.75

    def test_success_rate_zero_steps(self):
        """success_rate is 1.0 for zero steps."""
        analysis = ExecutionAnalysis(
            total_steps=0,
            completed_steps=0,
            successful_steps=0,
            failed_steps=0,
            empty_steps=0,
            total_results=0,
            execution_time_ms=0,
        )

        assert analysis.success_rate == 1.0

    def test_empty_rate_calculation(self):
        """empty_rate is calculated correctly."""
        analysis = ExecutionAnalysis(
            total_steps=4,
            completed_steps=4,
            successful_steps=4,
            failed_steps=0,
            empty_steps=2,
            total_results=5,
            execution_time_ms=500,
        )

        assert analysis.empty_rate == 0.5

    def test_is_complete_failure(self):
        """is_complete_failure is True when all steps failed."""
        analysis = ExecutionAnalysis(
            total_steps=3,
            completed_steps=3,
            successful_steps=0,
            failed_steps=3,
            empty_steps=0,
            total_results=0,
            execution_time_ms=500,
        )

        assert analysis.is_complete_failure

    def test_is_partial_failure(self):
        """is_partial_failure is True when some (not all) steps failed."""
        analysis = ExecutionAnalysis(
            total_steps=3,
            completed_steps=3,
            successful_steps=2,
            failed_steps=1,
            empty_steps=0,
            total_results=5,
            execution_time_ms=500,
        )

        assert analysis.is_partial_failure
        assert not analysis.is_complete_failure


# ============================================================================
# Test: RePlanResult Model
# ============================================================================


class TestRePlanResultModel:
    """Tests for RePlanResult Pydantic model."""

    def test_create_valid_result(self):
        """Can create a valid RePlanResult."""
        result = RePlanResult(
            decision=RePlanDecision.PROCEED,
            trigger=RePlanTrigger.NONE,
            reasoning="All steps successful",
        )

        assert result.decision == RePlanDecision.PROCEED
        assert result.confidence == 1.0  # Default

    def test_confidence_validation(self):
        """Confidence must be between 0 and 1."""
        result = RePlanResult(
            decision=RePlanDecision.PROCEED,
            trigger=RePlanTrigger.NONE,
            confidence=0.85,
            reasoning="Test",
        )

        assert result.confidence == 0.85

        # Should raise on invalid values
        with pytest.raises(ValueError):
            RePlanResult(
                decision=RePlanDecision.PROCEED,
                trigger=RePlanTrigger.NONE,
                confidence=1.5,  # Invalid
                reasoning="Test",
            )
