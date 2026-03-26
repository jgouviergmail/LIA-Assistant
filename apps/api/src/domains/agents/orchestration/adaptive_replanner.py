"""
Adaptive Re-Planner - Intelligent recovery from execution failures.

INTELLIPLANNER Phase E: Post-execution analysis and re-planning decisions.

This module provides intelligent re-planning when plan execution encounters issues:
- Empty results (tools returned nothing)
- Partial failures (some steps failed)
- Semantic mismatch (results don't match user intent)
- Dependency errors (missing data from previous steps)

Architecture:
    - Analyzes completed_steps after parallel execution
    - Detects failure patterns that may benefit from re-planning
    - Makes data-driven decisions about recovery strategies
    - Integrates with existing SemanticValidator for intent checking
    - No LLM calls by default (rule-based decisions for speed)

Design Goals:
    - Enable autonomous recovery from transient failures
    - Maintain user trust through transparent re-planning
    - Limit re-planning attempts to prevent infinite loops
    - Production-ready with metrics and logging

Integration:
    Called from task_orchestrator_node.py after execute_plan_parallel()
    returns. If re-planning is needed, can regenerate plan via planner_node.

References:
    - semantic_validator.py: Reuses validation patterns
    - parallel_executor.py: Source of completed_steps data
    - task_orchestrator_node.py: Integration point

Created: 2025-12-03 (INTELLIPLANNER Phase E)
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.i18n import _
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

logger = structlog.get_logger(__name__)


# ============================================================================
# Enums for Re-Planning Decisions
# ============================================================================


class RePlanTrigger(str, Enum):
    """
    Triggers that indicate re-planning may be beneficial.

    Each trigger represents a specific failure pattern detected after
    plan execution that might be recoverable through re-planning.
    """

    # Result-based triggers
    EMPTY_RESULTS = "empty_results"  # All tools returned no results
    PARTIAL_EMPTY = "partial_empty"  # Some tools returned no results
    PARTIAL_FAILURE = "partial_failure"  # Some steps failed with errors

    # Semantic triggers
    SEMANTIC_MISMATCH = "semantic_mismatch"  # Results don't match intent

    # Dependency triggers
    DEPENDENCY_ERROR = "dependency_error"  # Missing data from dependencies
    REFERENCE_ERROR = "reference_error"  # $steps.X.field couldn't resolve

    # Performance triggers
    TIMEOUT = "timeout"  # Execution exceeded time limit

    # No trigger (execution successful)
    NONE = "none"


class RePlanDecision(str, Enum):
    """
    Decisions about how to handle detected triggers.

    The replanner analyzes triggers and context to make one of these decisions.
    """

    # Continue normally (no re-planning needed)
    PROCEED = "proceed"

    # Re-run same plan (transient failure, retry may succeed)
    RETRY_SAME = "retry_same"

    # Generate modified plan (adjust parameters/approach)
    REPLAN_MODIFIED = "replan_modified"

    # Generate completely new plan (different strategy needed)
    REPLAN_NEW = "replan_new"

    # Ask user for clarification (ambiguous situation)
    ESCALATE_USER = "escalate_user"

    # Abort and explain failure (unrecoverable)
    ABORT = "abort"


class RecoveryStrategy(str, Enum):
    """
    Specific strategies for recovery when re-planning.

    Used to guide plan modification when REPLAN_MODIFIED is chosen.
    """

    # Broaden search criteria
    BROADEN_SEARCH = "broaden_search"

    # Use alternative data source
    ALTERNATIVE_SOURCE = "alternative_source"

    # Reduce scope (do less)
    REDUCE_SCOPE = "reduce_scope"

    # Skip optional steps
    SKIP_OPTIONAL = "skip_optional"

    # Add verification step
    ADD_VERIFICATION = "add_verification"

    # No specific strategy
    NONE = "none"


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class StepAnalysis:
    """Analysis of a single executed step."""

    step_id: str
    tool_name: str | None
    success: bool
    has_results: bool
    result_count: int
    error: str | None
    execution_time_ms: int

    @property
    def is_empty(self) -> bool:
        """Step succeeded but returned no meaningful results."""
        return self.success and not self.has_results


@dataclass
class ExecutionAnalysis:
    """Aggregated analysis of plan execution."""

    total_steps: int
    completed_steps: int
    successful_steps: int
    failed_steps: int
    empty_steps: int  # Successful but returned no results
    total_results: int
    execution_time_ms: int
    step_analyses: list[StepAnalysis] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Fraction of steps that succeeded."""
        if self.total_steps == 0:
            return 1.0
        return self.successful_steps / self.total_steps

    @property
    def empty_rate(self) -> float:
        """Fraction of successful steps that returned no results."""
        if self.successful_steps == 0:
            return 0.0
        return self.empty_steps / self.successful_steps

    @property
    def is_complete_failure(self) -> bool:
        """All steps failed."""
        return self.successful_steps == 0 and self.total_steps > 0

    @property
    def is_partial_failure(self) -> bool:
        """Some steps failed but not all."""
        return 0 < self.failed_steps < self.total_steps

    @property
    def is_all_empty(self) -> bool:
        """All steps succeeded but returned no results."""
        return (
            self.successful_steps > 0
            and self.empty_steps == self.successful_steps
            and self.total_results == 0
        )


@dataclass
class RePlanContext:
    """
    Context for re-planning decision.

    Contains all information needed to decide whether and how to re-plan.
    """

    # Original request
    user_request: str
    user_language: str

    # Plan information
    execution_plan: ExecutionPlan
    plan_id: str

    # Execution results
    completed_steps: dict[str, Any]
    execution_analysis: ExecutionAnalysis

    # Re-planning state
    replan_attempt: int  # Current attempt number (0 = first execution)
    max_attempts: int  # Maximum allowed attempts

    # Optional context
    previous_triggers: list[RePlanTrigger] = field(default_factory=list)
    accumulated_errors: list[str] = field(default_factory=list)


class RePlanResult(BaseModel):
    """
    Result of re-planning analysis.

    Contains the decision, reasoning, and any guidance for re-planning.
    """

    # Core decision
    decision: RePlanDecision = Field(description="Decision about re-planning")
    trigger: RePlanTrigger = Field(description="What triggered re-planning analysis")

    # Decision context
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=1.0,
        description="Confidence in the decision (0.0-1.0)",
    )
    reasoning: str = Field(description="Explanation of the decision")

    # Recovery guidance (if re-planning)
    recovery_strategy: RecoveryStrategy = Field(
        default=RecoveryStrategy.NONE,
        description="Suggested strategy for recovery",
    )
    modified_parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Suggested parameter modifications",
    )
    user_message: str | None = Field(
        default=None,
        description="Message to show user (for ESCALATE_USER or ABORT)",
    )

    # Retry context (for RETRY_SAME decision)
    failed_step_id: str | None = Field(
        default=None,
        description="ID of the step that failed (for RETRY_SAME)",
    )
    retry_attempt: int = Field(
        default=0,
        description="Current retry attempt number (for RETRY_SAME)",
    )

    # Metrics
    analysis_duration_ms: int = Field(
        default=0,
        description="Time taken for analysis in milliseconds",
    )


# ============================================================================
# Adaptive Re-Planner Service
# ============================================================================


class AdaptiveRePlanner:
    """
    Intelligent re-planning service for execution failures.

    Analyzes execution results and decides whether re-planning might help.
    Uses rule-based heuristics (no LLM calls) for fast decisions.

    Design Philosophy:
        - Fast: Rule-based, no LLM calls (< 10ms typical)
        - Conservative: Prefer PROCEED over unnecessary re-planning
        - Transparent: Clear reasoning for all decisions
        - Safe: Hard limits on re-planning attempts

    Example:
        >>> replanner = AdaptiveRePlanner()
        >>> context = RePlanContext(
        ...     user_request="Search for contacts named John",
        ...     execution_plan=plan,
        ...     completed_steps=results,
        ...     execution_analysis=analysis,
        ...     replan_attempt=0,
        ...     max_attempts=3,
        ... )
        >>> result = replanner.analyze_and_decide(context)
        >>> if result.decision == RePlanDecision.PROCEED:
        ...     # Continue to response_node
        ... elif result.decision == RePlanDecision.REPLAN_MODIFIED:
        ...     # Regenerate plan with modifications
    """

    def __init__(
        self,
        max_attempts: int | None = None,
        empty_threshold: float | None = None,
    ) -> None:
        """
        Initialize adaptive re-planner.

        Args:
            max_attempts: Maximum re-planning attempts before giving up.
                         Defaults to settings.adaptive_replanning_max_attempts.
            empty_threshold: Fraction of empty results that triggers re-planning.
                            Defaults to settings.adaptive_replanning_empty_threshold.
        """
        self._max_attempts = max_attempts or settings.adaptive_replanning_max_attempts
        self._empty_threshold = empty_threshold or settings.adaptive_replanning_empty_threshold

        logger.debug(
            "adaptive_replanner_initialized",
            max_attempts=self._max_attempts,
            empty_threshold=self._empty_threshold,
        )

    def analyze_and_decide(self, context: RePlanContext) -> RePlanResult:
        """
        Analyze execution results and decide on re-planning.

        This is the main entry point for the re-planner. It analyzes the
        execution results and returns a decision about whether and how
        to re-plan.

        Args:
            context: Complete context for decision-making

        Returns:
            RePlanResult with decision and guidance

        Performance:
            - Target: < 10ms (no LLM calls)
            - Rule-based heuristics only
        """
        start_time = time.time()

        # Step 1: Check if re-planning is even possible
        if context.replan_attempt >= context.max_attempts:
            logger.info(
                "replan_max_attempts_reached",
                plan_id=context.plan_id,
                attempt=context.replan_attempt,
                max_attempts=context.max_attempts,
            )
            return self._create_result(
                decision=RePlanDecision.ABORT,
                trigger=RePlanTrigger.NONE,
                reasoning=f"Maximum re-planning attempts ({context.max_attempts}) reached",
                user_message=self._get_abort_message(context),
                start_time=start_time,
            )

        # Step 2: Detect trigger (what might warrant re-planning)
        trigger = self._detect_trigger(context)

        # Step 3: If no trigger, proceed normally
        if trigger == RePlanTrigger.NONE:
            logger.debug(
                "replan_not_needed",
                plan_id=context.plan_id,
                success_rate=context.execution_analysis.success_rate,
            )
            return self._create_result(
                decision=RePlanDecision.PROCEED,
                trigger=trigger,
                reasoning="Execution completed successfully, no re-planning needed",
                start_time=start_time,
            )

        # Step 4: Decide based on trigger
        decision, strategy, reasoning, user_message = self._decide_for_trigger(trigger, context)

        # Step 4.5: Extract failed_step_id for RETRY_SAME decisions
        failed_step_id = None
        if decision == RePlanDecision.RETRY_SAME:
            # Get the first failed step ID
            failed_steps = [s for s in context.execution_analysis.step_analyses if not s.success]
            if failed_steps:
                failed_step_id = failed_steps[0].step_id

        # Step 5: Log decision
        logger.info(
            "replan_decision_made",
            plan_id=context.plan_id,
            trigger=trigger.value,
            decision=decision.value,
            strategy=strategy.value,
            attempt=context.replan_attempt,
            reasoning=reasoning,
            failed_step_id=failed_step_id,
        )

        # Track metrics
        from src.infrastructure.observability.metrics_agents import (
            adaptive_replanner_decisions_total,
            adaptive_replanner_triggers_total,
        )

        adaptive_replanner_triggers_total.labels(trigger=trigger.value).inc()
        adaptive_replanner_decisions_total.labels(decision=decision.value).inc()

        return self._create_result(
            decision=decision,
            trigger=trigger,
            reasoning=reasoning,
            recovery_strategy=strategy,
            user_message=user_message,
            start_time=start_time,
            failed_step_id=failed_step_id,
            retry_attempt=context.replan_attempt,
        )

    def _detect_trigger(self, context: RePlanContext) -> RePlanTrigger:
        """
        Detect what (if anything) should trigger re-planning consideration.

        Checks various failure patterns in priority order.

        Args:
            context: Execution context

        Returns:
            The detected trigger, or NONE if execution was successful
        """
        analysis = context.execution_analysis

        # Priority 1: Complete failure (all steps failed)
        if analysis.is_complete_failure:
            logger.debug(
                "trigger_detected_complete_failure",
                plan_id=context.plan_id,
            )
            return RePlanTrigger.PARTIAL_FAILURE

        # Priority 2: Partial failure (some steps failed)
        if analysis.is_partial_failure:
            logger.debug(
                "trigger_detected_partial_failure",
                plan_id=context.plan_id,
                failed_steps=analysis.failed_steps,
            )
            return RePlanTrigger.PARTIAL_FAILURE

        # Priority 3: All empty results
        if analysis.is_all_empty:
            logger.debug(
                "trigger_detected_all_empty",
                plan_id=context.plan_id,
            )
            return RePlanTrigger.EMPTY_RESULTS

        # Priority 4: High empty rate (above threshold)
        if analysis.empty_rate >= self._empty_threshold:
            logger.debug(
                "trigger_detected_partial_empty",
                plan_id=context.plan_id,
                empty_rate=analysis.empty_rate,
                threshold=self._empty_threshold,
            )
            return RePlanTrigger.PARTIAL_EMPTY

        # Priority 5: Check for dependency/reference errors in results
        for _step_id, step_data in context.completed_steps.items():
            if isinstance(step_data, dict):
                error = step_data.get("error", "")
                if error:
                    if "reference" in error.lower() or "$steps" in error:
                        return RePlanTrigger.REFERENCE_ERROR
                    if "dependency" in error.lower():
                        return RePlanTrigger.DEPENDENCY_ERROR

        # No trigger detected
        return RePlanTrigger.NONE

    def _decide_for_trigger(
        self,
        trigger: RePlanTrigger,
        context: RePlanContext,
    ) -> tuple[RePlanDecision, RecoveryStrategy, str, str | None]:
        """
        Make decision based on detected trigger.

        Args:
            trigger: The detected trigger
            context: Execution context

        Returns:
            Tuple of (decision, strategy, reasoning, user_message)
        """
        match trigger:
            case RePlanTrigger.EMPTY_RESULTS:
                return self._handle_empty_results(context)

            case RePlanTrigger.PARTIAL_EMPTY:
                return self._handle_partial_empty(context)

            case RePlanTrigger.PARTIAL_FAILURE:
                return self._handle_partial_failure(context)

            case RePlanTrigger.REFERENCE_ERROR:
                return self._handle_reference_error(context)

            case RePlanTrigger.DEPENDENCY_ERROR:
                return self._handle_dependency_error(context)

            case RePlanTrigger.TIMEOUT:
                return self._handle_timeout(context)

            case _:
                return (
                    RePlanDecision.PROCEED,
                    RecoveryStrategy.NONE,
                    "Unknown trigger, proceeding normally",
                    None,
                )

    def _handle_empty_results(
        self,
        context: RePlanContext,
    ) -> tuple[RePlanDecision, RecoveryStrategy, str, str | None]:
        """
        Handle case where all tools returned no results.

        Strategy: On first attempt, try broadening search. On second attempt,
        escalate to user for clarification.
        """
        if context.replan_attempt == 0:
            # First attempt: try broader search
            return (
                RePlanDecision.REPLAN_MODIFIED,
                RecoveryStrategy.BROADEN_SEARCH,
                "All tools returned empty results. Will retry with broader search criteria.",
                None,
            )
        elif context.replan_attempt == 1:
            # Second attempt: try alternative approach
            return (
                RePlanDecision.REPLAN_MODIFIED,
                RecoveryStrategy.ALTERNATIVE_SOURCE,
                "Broader search still returned no results. Trying alternative approach.",
                None,
            )
        else:
            # Third+ attempt: escalate to user
            return (
                RePlanDecision.ESCALATE_USER,
                RecoveryStrategy.NONE,
                "Multiple attempts returned no results. Asking user for clarification.",
                _(
                    "I couldn't find any results matching your request. "
                    "Could you clarify or rephrase?"
                ),
            )

    def _handle_partial_empty(
        self,
        context: RePlanContext,
    ) -> tuple[RePlanDecision, RecoveryStrategy, str, str | None]:
        """
        Handle case where some tools returned results but others didn't.

        Strategy: Proceed if we have enough results, otherwise suggest
        skipping empty sources.
        """
        analysis = context.execution_analysis

        # If we have some results, usually better to proceed
        if analysis.total_results > 0:
            return (
                RePlanDecision.PROCEED,
                RecoveryStrategy.NONE,
                f"Some steps returned empty results but {analysis.total_results} results found overall. Proceeding.",
                None,
            )

        # No results at all despite partial success
        if context.replan_attempt == 0:
            return (
                RePlanDecision.REPLAN_MODIFIED,
                RecoveryStrategy.BROADEN_SEARCH,
                "Steps executed but returned no results. Trying broader criteria.",
                None,
            )

        return (
            RePlanDecision.PROCEED,
            RecoveryStrategy.NONE,
            "Partial empty results after retry, proceeding with available data.",
            None,
        )

    def _handle_partial_failure(
        self,
        context: RePlanContext,
    ) -> tuple[RePlanDecision, RecoveryStrategy, str, str | None]:
        """
        Handle case where some steps failed with errors.

        Strategy: On first attempt, retry same plan (may be transient).
        On second attempt, try skipping failed steps if optional.
        """
        analysis = context.execution_analysis

        # Collect failed step info
        failed_steps = [s for s in analysis.step_analyses if not s.success]
        failed_names = [s.tool_name for s in failed_steps if s.tool_name]

        if context.replan_attempt == 0:
            # First attempt: retry (may be transient)
            return (
                RePlanDecision.RETRY_SAME,
                RecoveryStrategy.NONE,
                f"Steps {failed_names} failed. Retrying (may be transient).",
                None,
            )
        elif context.replan_attempt == 1:
            # Second attempt: try skipping failed steps
            return (
                RePlanDecision.REPLAN_MODIFIED,
                RecoveryStrategy.SKIP_OPTIONAL,
                f"Steps {failed_names} still failing. Trying without optional steps.",
                None,
            )
        else:
            # If we have some results, proceed anyway
            if analysis.total_results > 0:
                return (
                    RePlanDecision.PROCEED,
                    RecoveryStrategy.NONE,
                    f"Some steps failed but {analysis.total_results} results available. Proceeding.",
                    None,
                )
            # No results: abort
            return (
                RePlanDecision.ABORT,
                RecoveryStrategy.NONE,
                f"Multiple retry attempts failed for steps {failed_names}.",
                _("Sorry, some operations failed after multiple attempts: {operations}").format(
                    operations=", ".join(failed_names)
                ),
            )

    def _handle_reference_error(
        self,
        context: RePlanContext,
    ) -> tuple[RePlanDecision, RecoveryStrategy, str, str | None]:
        """
        Handle case where $steps.X.field reference couldn't resolve.

        Strategy: This usually indicates a plan structure problem.
        Regenerate with verification step.
        """
        if context.replan_attempt == 0:
            return (
                RePlanDecision.REPLAN_MODIFIED,
                RecoveryStrategy.ADD_VERIFICATION,
                "Step reference couldn't resolve. Adding verification step.",
                None,
            )

        return (
            RePlanDecision.ESCALATE_USER,
            RecoveryStrategy.NONE,
            "Reference resolution failed multiple times.",
            _("The required data could not be found. Could you clarify your request?"),
        )

    def _handle_dependency_error(
        self,
        context: RePlanContext,
    ) -> tuple[RePlanDecision, RecoveryStrategy, str, str | None]:
        """
        Handle case where step dependency data was missing.

        Strategy: Similar to reference error, but may need different approach.
        """
        if context.replan_attempt == 0:
            return (
                RePlanDecision.REPLAN_MODIFIED,
                RecoveryStrategy.ADD_VERIFICATION,
                "Dependency data missing. Reorganizing plan dependencies.",
                None,
            )

        return (
            RePlanDecision.ABORT,
            RecoveryStrategy.NONE,
            "Dependency error persists after retry.",
            _("A dependency error occurred between steps."),
        )

    def _handle_timeout(
        self,
        context: RePlanContext,
    ) -> tuple[RePlanDecision, RecoveryStrategy, str, str | None]:
        """
        Handle case where execution exceeded time limit.

        Strategy: Try reducing scope to fit within limits.
        """
        if context.replan_attempt == 0:
            return (
                RePlanDecision.REPLAN_MODIFIED,
                RecoveryStrategy.REDUCE_SCOPE,
                "Execution timed out. Reducing scope.",
                None,
            )

        return (
            RePlanDecision.ABORT,
            RecoveryStrategy.NONE,
            "Execution still too slow after scope reduction.",
            _("The operation is taking too long. Try a more specific request."),
        )

    def _get_abort_message(self, context: RePlanContext) -> str:
        """Generate user-facing message when aborting."""
        if context.accumulated_errors:
            errors_summary = "; ".join(context.accumulated_errors[:3])
            return _(
                "Unable to execute this request after multiple attempts. Errors: {errors}"
            ).format(errors=errors_summary)
        return _("Unable to execute this request after multiple attempts.")

    def _create_result(
        self,
        decision: RePlanDecision,
        trigger: RePlanTrigger,
        reasoning: str,
        start_time: float,
        recovery_strategy: RecoveryStrategy = RecoveryStrategy.NONE,
        user_message: str | None = None,
        modified_parameters: dict[str, Any] | None = None,
        failed_step_id: str | None = None,
        retry_attempt: int = 0,
    ) -> RePlanResult:
        """Create RePlanResult with timing."""
        duration_ms = int((time.time() - start_time) * 1000)

        return RePlanResult(
            decision=decision,
            trigger=trigger,
            reasoning=reasoning,
            recovery_strategy=recovery_strategy,
            user_message=user_message,
            modified_parameters=modified_parameters or {},
            failed_step_id=failed_step_id,
            retry_attempt=retry_attempt,
            analysis_duration_ms=duration_ms,
        )


# ============================================================================
# Helper Functions
# ============================================================================


def analyze_execution_results(
    execution_plan: ExecutionPlan,
    completed_steps: dict[str, Any],
) -> ExecutionAnalysis:
    """
    Analyze completed_steps to extract execution metrics.

    Args:
        execution_plan: The executed plan
        completed_steps: Results from parallel_executor

    Returns:
        ExecutionAnalysis with aggregated metrics
    """
    step_analyses: list[StepAnalysis] = []
    total_results = 0
    total_time = 0

    for step in execution_plan.steps:
        step_id = step.step_id
        step_data = completed_steps.get(step_id, {})

        if isinstance(step_data, dict):
            success = step_data.get("success", True)
            error = step_data.get("error")
            exec_time = step_data.get("execution_time_ms", 0)

            # Count results using centralized domain registry + generic fallback keys
            from src.domains.agents.utils.type_domain_mapping import ALL_RESULT_KEYS

            result_count = 0
            has_results = False

            # Check all known domain result keys + generic fallback patterns
            _result_keys = ALL_RESULT_KEYS | {
                "results",
                "data",
                "items",  # generic fallback patterns
                "weather",
                "task_lists",  # legacy keys (tools may use singular form)
            }
            for key in _result_keys:
                if key in step_data:
                    items = step_data[key]
                    if isinstance(items, list):
                        result_count += len(items)
                        if items:
                            has_results = True
                    elif items:
                        result_count += 1
                        has_results = True

            # Action tools (UnifiedToolOutput.action_success) store their
            # confirmation message in a "result" key (singular).  This is NOT
            # a data-query result but it IS a meaningful result that must not
            # be treated as "empty".
            if not has_results and "result" in step_data:
                result_value = step_data["result"]
                if result_value:
                    has_results = True
                    result_count = max(result_count, 1)

            # Also check for count/total field
            count_value = step_data.get("count") or step_data.get("total") or 0
            if count_value > 0:
                has_results = True
                if result_count == 0:
                    result_count = count_value

        else:
            # Non-dict result (legacy format)
            success = True
            error = None
            exec_time = 0
            result_count = 1 if step_data else 0
            has_results = bool(step_data)

        step_analyses.append(
            StepAnalysis(
                step_id=step_id,
                tool_name=step.tool_name,
                success=success,
                has_results=has_results,
                result_count=result_count,
                error=error,
                execution_time_ms=exec_time,
            )
        )

        total_results += result_count
        total_time += exec_time

    # Aggregate metrics
    total_steps = len(execution_plan.steps)
    completed = len(completed_steps)
    successful = sum(1 for s in step_analyses if s.success)
    failed = sum(1 for s in step_analyses if not s.success)
    empty = sum(1 for s in step_analyses if s.is_empty)

    return ExecutionAnalysis(
        total_steps=total_steps,
        completed_steps=completed,
        successful_steps=successful,
        failed_steps=failed,
        empty_steps=empty,
        total_results=total_results,
        execution_time_ms=total_time,
        step_analyses=step_analyses,
    )


def should_trigger_replan(
    execution_plan: ExecutionPlan,
    completed_steps: dict[str, Any],
    empty_threshold: float | None = None,
) -> tuple[bool, RePlanTrigger]:
    """
    Quick check if re-planning should be considered.

    This is a lightweight function for fast decision-making without
    full context construction. Use for initial filtering before
    creating full RePlanContext.

    Args:
        execution_plan: The executed plan
        completed_steps: Results from parallel_executor
        empty_threshold: Custom threshold (defaults to settings)

    Returns:
        Tuple of (should_consider_replan, trigger)
    """
    threshold = empty_threshold or settings.adaptive_replanning_empty_threshold
    analysis = analyze_execution_results(execution_plan, completed_steps)

    # Check failure conditions
    if analysis.is_complete_failure:
        return True, RePlanTrigger.PARTIAL_FAILURE

    if analysis.is_partial_failure:
        return True, RePlanTrigger.PARTIAL_FAILURE

    if analysis.is_all_empty:
        return True, RePlanTrigger.EMPTY_RESULTS

    if analysis.empty_rate >= threshold:
        return True, RePlanTrigger.PARTIAL_EMPTY

    return False, RePlanTrigger.NONE


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "RePlanTrigger",
    "RePlanDecision",
    "RecoveryStrategy",
    "StepAnalysis",
    "ExecutionAnalysis",
    "RePlanContext",
    "RePlanResult",
    "AdaptiveRePlanner",
    "analyze_execution_results",
    "should_trigger_replan",
]
