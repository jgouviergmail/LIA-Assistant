"""
AutonomousExecutor - Self-Healing Execution with Safeguards.

Architecture v3 - Intelligence, Autonomie, Pertinence.

This executor provides:
1. Self-healing: If a tool fails, tries alternatives
2. Intelligent retry: Not blind retry, but adapted strategies
3. Graceful degradation: If all fails, returns useful message
4. Proactivity: Suggests actions after execution

SAFEGUARDS ANTI-LOOP:
- max_recovery_attempts per step (default: 3)
- max_total_recoveries per plan (default: 5)
- recovery_timeout global (default: 30s)
- strategy_blacklist to avoid repeating failed strategies
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from langchain_core.runnables import RunnableConfig

from src.core.config.agents import V3ExecutorConfig, get_v3_executor_config
from src.core.i18n_v3 import V3Messages
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep
    from src.domains.agents.services.feedback_loop import FeedbackLoopService

logger = get_logger(__name__)


class RecoveryStrategy(Enum):
    """Recovery strategies on failure."""

    RETRY_SAME = "retry_same"  # Retry the same tool
    BROADEN_SEARCH = "broaden_search"  # Widen search terms
    ALTERNATIVE_TOOL = "alternative"  # Use alternative tool
    ALTERNATIVE_FIELD = "alt_field"  # Search by another field
    SKIP_AND_CONTINUE = "skip"  # Skip step and continue
    ABORT_GRACEFULLY = "abort"  # Abort with explanatory message


@dataclass
class ExecutionAttempt:
    """Trace of an execution attempt."""

    step_id: str
    tool_name: str
    parameters: dict[str, Any]
    success: bool
    result: Any | None = None
    error: str | None = None
    recovery_strategy: RecoveryStrategy | None = None
    duration_ms: float = 0.0


@dataclass
class AutonomousExecutionResult:
    """Result of autonomous execution."""

    success: bool
    results: list[Any]
    attempts: list[ExecutionAttempt] = field(default_factory=list)
    recoveries_performed: int = 0
    final_message: str = ""
    proactive_suggestions: list[str] = field(default_factory=list)
    total_duration_ms: float = 0.0


class AutonomousExecutor:
    """
    Autonomous Executor with self-healing.

    CAPABILITIES:
    1. Self-healing: If a tool fails, tries alternatives
    2. Intelligent retry: Not blind retry, but adapted strategies
    3. Graceful degradation: If all fails, returns useful message
    4. Proactivity: Suggests actions after execution

    DIFFERENCES with current executor:
    - Current: failure = failure, end of story
    - This: failure = opportunity for recovery

    SAFEGUARDS ANTI-LOOP:
    - max_recovery_attempts per step (configurable via .env)
    - max_total_recoveries per plan (configurable via .env)
    - recovery_timeout global (configurable via .env)
    - strategy_blacklist to avoid repeating failed strategies
    """

    def __init__(
        self,
        feedback_loop: FeedbackLoopService | None = None,
        config: V3ExecutorConfig | None = None,
    ):
        # Load config from settings if not provided
        self._config = config or get_v3_executor_config()

        # === SAFEGUARDS CONFIGURATION (from V3ExecutorConfig) ===
        self.MAX_RECOVERY_PER_STEP = self._config.max_recovery_per_step
        self.MAX_TOTAL_RECOVERIES = self._config.max_total_recoveries
        self.RECOVERY_TIMEOUT_MS = self._config.recovery_timeout_ms
        self.CIRCUIT_BREAKER_THRESHOLD = self._config.circuit_breaker_threshold

        self.max_recovery_attempts = self.MAX_RECOVERY_PER_STEP
        self._recovery_strategies = self._build_recovery_strategies()
        self.feedback_loop = feedback_loop

        # Runtime safeguard state
        self._total_recoveries = 0
        self._consecutive_failures = 0
        self._failed_strategies: set[tuple[str, str]] = set()  # (step_id, strategy)
        self._start_time: float | None = None
        self._step_recovery_counts: dict[str, int] = {}

    def _reset_safeguards(self) -> None:
        """Reset safeguards for new execution."""
        self._total_recoveries = 0
        self._consecutive_failures = 0
        self._failed_strategies.clear()
        self._start_time = None
        self._step_recovery_counts.clear()

    def _check_safeguards(self, step_id: str) -> tuple[bool, str]:
        """
        Check if we should continue recovery attempts.

        Returns: (can_continue, reason_if_stopped)
        """
        # Check timeout
        if self._start_time:
            elapsed_ms = (time.time() - self._start_time) * 1000
            if elapsed_ms > self.RECOVERY_TIMEOUT_MS:
                return False, f"Recovery timeout ({self.RECOVERY_TIMEOUT_MS}ms)"

        # Check total recoveries
        if self._total_recoveries >= self.MAX_TOTAL_RECOVERIES:
            return False, f"Max total recoveries reached ({self.MAX_TOTAL_RECOVERIES})"

        # Check circuit breaker
        if self._consecutive_failures >= self.CIRCUIT_BREAKER_THRESHOLD:
            return (
                False,
                f"Circuit breaker triggered ({self.CIRCUIT_BREAKER_THRESHOLD} consecutive failures)",
            )

        # Check per-step limit
        step_count = self._step_recovery_counts.get(step_id, 0)
        if step_count >= self.MAX_RECOVERY_PER_STEP:
            return False, f"Max recoveries for step {step_id} ({self.MAX_RECOVERY_PER_STEP})"

        return True, ""

    def _is_strategy_blacklisted(
        self,
        step_id: str,
        strategy: RecoveryStrategy,
    ) -> bool:
        """Check if strategy already failed for this step."""
        return (step_id, strategy.value) in self._failed_strategies

    def _blacklist_strategy(
        self,
        step_id: str,
        strategy: RecoveryStrategy,
    ) -> None:
        """Blacklist a strategy that failed."""
        self._failed_strategies.add((step_id, strategy.value))

    async def execute_with_recovery(
        self,
        intelligence: QueryIntelligence,
        plan: ExecutionPlan,
        config: RunnableConfig,
    ) -> AutonomousExecutionResult:
        """
        Execute plan with automatic recovery.

        Flow:
        1. Execute each step
        2. If failure → attempt recovery (with safeguards)
        3. If recovery fails → graceful degradation
        4. Always return something useful

        SAFEGUARDS:
        - Max 3 recoveries per step
        - Max 5 total recoveries
        - Timeout global 30s
        - Circuit breaker after 3 consecutive failures
        """
        execution_start = time.time()

        # Reset safeguards for new execution
        self._reset_safeguards()
        self._start_time = time.time()

        # Get preemptive strategies from feedback loop if available
        if self.feedback_loop:
            preemptive = await self.feedback_loop.suggest_preemptive_strategies(intelligence)
            if preemptive:
                # Prepend to fallback strategies
                existing = list(intelligence.fallback_strategies)
                intelligence = intelligence._with_updated_fallbacks(preemptive + existing)  # type: ignore

        attempts: list[ExecutionAttempt] = []
        results: list[Any] = []
        recoveries = 0

        for step in plan.steps:
            # Check global safeguards before each step
            can_continue, stop_reason = self._check_safeguards(step.step_id)
            if not can_continue:
                logger.warning(f"Execution stopped: {stop_reason}")
                return AutonomousExecutionResult(
                    success=False,
                    results=results,
                    attempts=attempts,
                    recoveries_performed=recoveries,
                    final_message=f"Execution stopped: {stop_reason}",
                    total_duration_ms=(time.time() - execution_start) * 1000,
                )

            attempt = await self._execute_step(
                step=step,
                config=config,
                previous_results=results,
            )
            attempts.append(attempt)

            if attempt.success:
                results.append(attempt.result)
                self._consecutive_failures = 0  # Reset circuit breaker
            else:
                self._consecutive_failures += 1

                # Check safeguards before recovery
                can_continue, stop_reason = self._check_safeguards(step.step_id)
                if not can_continue:
                    return AutonomousExecutionResult(
                        success=False,
                        results=results,
                        attempts=attempts,
                        recoveries_performed=recoveries,
                        final_message=f"Recovery stopped: {stop_reason}",
                        total_duration_ms=(time.time() - execution_start) * 1000,
                    )

                # Attempt recovery with safeguards
                recovery_attempt = await self._attempt_recovery_with_safeguards(
                    failed_attempt=attempt,
                    step=step,
                    intelligence=intelligence,
                    config=config,
                    previous_results=results,
                )

                if recovery_attempt and recovery_attempt.success:
                    results.append(recovery_attempt.result)
                    attempts.append(recovery_attempt)
                    recoveries += 1
                    self._total_recoveries += 1
                    self._consecutive_failures = 0

                    # Record success in feedback loop
                    if self.feedback_loop and recovery_attempt.recovery_strategy:
                        await self._record_recovery(
                            intelligence=intelligence,
                            attempt=recovery_attempt,
                            success=True,
                        )
                else:
                    # Graceful degradation
                    partial_message = self._build_partial_success_message(
                        step=step,
                        results=results,
                        error=attempt.error,
                    )
                    return AutonomousExecutionResult(
                        success=False,
                        results=results,
                        attempts=attempts,
                        recoveries_performed=recoveries,
                        final_message=partial_message,
                        total_duration_ms=(time.time() - execution_start) * 1000,
                    )

        # Complete success
        proactive = self._get_proactive_suggestions(intelligence)

        return AutonomousExecutionResult(
            success=True,
            results=results,
            attempts=attempts,
            recoveries_performed=recoveries,
            proactive_suggestions=proactive,
            total_duration_ms=(time.time() - execution_start) * 1000,
        )

    async def _attempt_recovery_with_safeguards(
        self,
        failed_attempt: ExecutionAttempt,
        step: ExecutionStep,
        intelligence: QueryIntelligence,
        config: RunnableConfig,
        previous_results: list[Any],
    ) -> ExecutionAttempt | None:
        """
        Recovery with anti-loop safeguards.

        Checks:
        1. Strategy not blacklisted (already failed)
        2. Global limits respected
        """
        step_id = failed_attempt.step_id
        strategies = list(intelligence.fallback_strategies)

        # Increment per-step recovery count
        self._step_recovery_counts[step_id] = self._step_recovery_counts.get(step_id, 0) + 1

        for strategy_name in strategies:
            strategy = self._get_strategy(strategy_name)
            if not strategy:
                continue

            # Skip blacklisted strategies
            if self._is_strategy_blacklisted(step_id, strategy):
                logger.debug(f"Skipping blacklisted strategy {strategy.value} for {step_id}")
                continue

            recovery_params = self._apply_strategy(
                strategy=strategy,
                original_params=failed_attempt.parameters,
                tool_name=failed_attempt.tool_name,
            )

            if recovery_params:
                logger.info(f"Attempting recovery with {strategy.value} for {step_id}")

                new_attempt = await self._execute_step(
                    step=self._create_recovery_step(step, recovery_params, strategy),
                    config=config,
                    previous_results=previous_results,
                )
                new_attempt.recovery_strategy = strategy

                if new_attempt.success:
                    logger.info(f"Recovery succeeded with {strategy.value}")
                    return new_attempt
                else:
                    # Blacklist this strategy for this step
                    self._blacklist_strategy(step_id, strategy)
                    logger.debug(f"Blacklisted {strategy.value} for {step_id}")

                    # Record failure in feedback loop
                    if self.feedback_loop:
                        await self._record_recovery(
                            intelligence=intelligence,
                            attempt=new_attempt,
                            success=False,
                        )

        return None

    async def _execute_step(
        self,
        step: ExecutionStep,
        config: RunnableConfig,
        previous_results: list[Any],
    ) -> ExecutionAttempt:
        """Execute a step with error handling."""
        from src.domains.agents.registry import get_global_registry

        start_time = time.time()
        registry = get_global_registry()

        # Resolve parameters that reference previous results
        resolved_params = self._resolve_parameters(step.parameters, previous_results)

        tool = registry.get_tool(step.tool_name)  # type: ignore

        if not tool:
            return ExecutionAttempt(
                step_id=step.step_id,
                tool_name=step.tool_name or "unknown",
                parameters=resolved_params,
                success=False,
                error=f"Tool not found: {step.tool_name}",
                duration_ms=(time.time() - start_time) * 1000,
            )

        try:
            result = await tool.ainvoke(resolved_params, config=config)
            return ExecutionAttempt(
                step_id=step.step_id,
                tool_name=step.tool_name or "unknown",
                parameters=resolved_params,
                success=True,
                result=result,
                duration_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            logger.warning(f"Step {step.step_id} failed: {e}")
            return ExecutionAttempt(
                step_id=step.step_id,
                tool_name=step.tool_name or "unknown",
                parameters=resolved_params,
                success=False,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

    def _resolve_parameters(
        self,
        parameters: dict[str, Any],
        previous_results: list[Any],
    ) -> dict[str, Any]:
        """
        Resolve parameter references to previous results.

        Supports patterns like:
        - "$steps.0.result.field" → previous_results[0]["field"]
        - "$steps.step_1.exports[0]" → more complex references
        """
        resolved = {}

        for key, value in parameters.items():
            if isinstance(value, str) and value.startswith("$steps."):
                try:
                    resolved[key] = self._extract_reference(value, previous_results)
                except (IndexError, KeyError) as e:
                    logger.warning(f"Could not resolve reference {value}: {e}")
                    resolved[key] = value
            else:
                resolved[key] = value

        return resolved

    def _extract_reference(
        self,
        reference: str,
        previous_results: list[Any],
    ) -> Any:
        """Extract value from reference string."""
        # Simple implementation: "$steps.0.result.field"
        parts = reference.replace("$steps.", "").split(".")
        if len(parts) >= 1:
            try:
                idx = int(parts[0])
                if idx < len(previous_results):
                    result = previous_results[idx]
                    # Navigate through nested fields
                    for part in parts[1:]:
                        if isinstance(result, dict):
                            result = result.get(part, result)
                        elif isinstance(result, list) and part.isdigit():
                            result = result[int(part)]
                    return result
            except (ValueError, TypeError):
                pass
        return reference

    def _apply_strategy(
        self,
        strategy: RecoveryStrategy,
        original_params: dict[str, Any],
        tool_name: str,
    ) -> dict[str, Any] | None:
        """Apply a recovery strategy to parameters."""
        if strategy == RecoveryStrategy.BROADEN_SEARCH:
            # Widen search terms
            if "query" in original_params:
                words = original_params["query"].split()
                if len(words) > 1:
                    # Take just the first word (or last, depending on context)
                    return {**original_params, "query": words[0]}

        elif strategy == RecoveryStrategy.ALTERNATIVE_FIELD:
            # Search by another field
            if tool_name == "search_contacts":
                if "query" in original_params:
                    return {
                        **original_params,
                        "search_field": "email",  # Alternative: search by email
                    }

        elif strategy == RecoveryStrategy.RETRY_SAME:
            # Simple retry with same params (for transient errors)
            return original_params.copy()

        return None

    def _build_partial_success_message(
        self,
        step: ExecutionStep,
        results: list[Any],
        error: str | None,
        language: str = "fr",
    ) -> str:
        """
        Build an explanatory message in case of partial failure.

        IMPORTANT: Always be useful, even in case of failure.
        Uses i18n for multi-language support.
        """
        return V3Messages.get_partial_success_message(
            language=language,
            has_results=bool(results),
            tool_name=step.tool_name or "unknown",
            error=error or "",
        )

    def _get_proactive_suggestions(
        self,
        intelligence: QueryIntelligence,
        language: str = "fr",
    ) -> list[str]:
        """
        Get proactive suggestions based on intelligence.

        Uses i18n for multi-language support.
        """
        suggestions = []

        # Use anticipated needs from intelligence
        if intelligence.anticipated_needs:
            suggestions.extend(intelligence.anticipated_needs[:3])

        # Add implicit intents as suggestions (using i18n)
        if intelligence.implicit_intents:
            for intent in intelligence.implicit_intents[:2]:
                suggestion = V3Messages.get_proactive_suggestion(intent, language)
                if suggestion and suggestion != intent:  # Only add if translated
                    suggestions.append(suggestion)

        return suggestions[:4]  # Limit to 4 suggestions

    def _build_recovery_strategies(self) -> dict[str, list[RecoveryStrategy]]:
        """Configure recovery strategies by tool type."""
        return {
            "search": [
                RecoveryStrategy.BROADEN_SEARCH,
                RecoveryStrategy.ALTERNATIVE_FIELD,
            ],
            "send": [
                RecoveryStrategy.RETRY_SAME,
                RecoveryStrategy.SKIP_AND_CONTINUE,
            ],
            "create": [
                RecoveryStrategy.RETRY_SAME,
                RecoveryStrategy.ABORT_GRACEFULLY,
            ],
            "get": [
                RecoveryStrategy.RETRY_SAME,
            ],
            "list": [
                RecoveryStrategy.BROADEN_SEARCH,
            ],
        }

    def _get_strategy(self, strategy_name: str) -> RecoveryStrategy | None:
        """Convert strategy name to enum."""
        MAPPING = {
            "broaden_search_terms": RecoveryStrategy.BROADEN_SEARCH,
            "broaden_search": RecoveryStrategy.BROADEN_SEARCH,
            "try_alternative_field": RecoveryStrategy.ALTERNATIVE_FIELD,
            "search_by_email": RecoveryStrategy.ALTERNATIVE_FIELD,
            "search_by_phone": RecoveryStrategy.ALTERNATIVE_FIELD,
            "queue_for_later": RecoveryStrategy.SKIP_AND_CONTINUE,
            "save_draft": RecoveryStrategy.SKIP_AND_CONTINUE,
            "retry": RecoveryStrategy.RETRY_SAME,
        }
        return MAPPING.get(strategy_name)

    def _create_recovery_step(
        self,
        original_step: ExecutionStep,
        new_params: dict[str, Any],
        strategy: RecoveryStrategy,
    ) -> ExecutionStep:
        """Create a recovery step based on original."""
        from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType

        return ExecutionStep(
            step_id=f"{original_step.step_id}_recovery_{strategy.value}",
            step_type=StepType.TOOL,
            agent_name=original_step.agent_name,
            tool_name=original_step.tool_name,
            parameters=new_params,
            depends_on=[],
        )

    async def _record_recovery(
        self,
        intelligence: QueryIntelligence,
        attempt: ExecutionAttempt,
        success: bool,
    ) -> None:
        """Record recovery outcome in feedback loop."""
        if not self.feedback_loop or not attempt.recovery_strategy:
            return

        from src.domains.agents.services.feedback_loop import RecoveryOutcome

        await self.feedback_loop.record_recovery(
            original_query=intelligence.original_query,
            original_params=attempt.parameters,
            strategy=attempt.recovery_strategy.value,
            recovered_params=attempt.parameters,
            outcome=RecoveryOutcome.SUCCESS if success else RecoveryOutcome.FAILURE,
            domain=intelligence.primary_domain,
            tool_name=attempt.tool_name,
        )


# Singleton
_executor: AutonomousExecutor | None = None


def get_autonomous_executor() -> AutonomousExecutor:
    """Get singleton AutonomousExecutor instance."""
    global _executor
    if _executor is None:
        # Import here to avoid circular imports
        try:
            from src.domains.agents.services.feedback_loop import get_feedback_loop_service

            _executor = AutonomousExecutor(feedback_loop=get_feedback_loop_service())
        except ImportError:
            _executor = AutonomousExecutor()
    return _executor


def reset_executor() -> None:
    """Reset executor for testing."""
    global _executor
    _executor = None
