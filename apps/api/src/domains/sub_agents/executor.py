"""
Sub-Agent executor.

Executes sub-agents through a simplified direct pipeline that bypasses the
full LangGraph graph. Instead of compaction → router → planner → validator →
approval_gate → orchestrator → response, sub-agents use:

    instruction → SmartPlannerService.plan() → execute_plan_parallel() → LLM synthesis

This eliminates ghost dependencies, replanning loops, and HITL triggers inside
sub-agents while preserving all guard-rails (timeout, cancel, budget, token tracking).

Phase: F6 — Persistent Specialized Sub-Agents
"""

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import structlog
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, ValidationError
from src.domains.agents.analysis.query_intelligence import QueryIntelligence
from src.domains.sub_agents.constants import (
    SUBAGENT_DAILY_BUDGET_KEY_PREFIX,
    SUBAGENT_EXCLUDED_PLANNER_TOOLS,
    SUBAGENT_SYNTHESIS_PROMPT_NAME,
)
from src.domains.sub_agents.models import SubAgent, SubAgentStatus
from src.infrastructure.observability.metrics_subagent import (
    subagent_active_count,
    subagent_duration_seconds,
    subagent_errors_total,
    subagent_killed_total,
    subagent_spawned_total,
    subagent_tokens_in_total,
    subagent_tokens_out_total,
)

logger = structlog.get_logger(__name__)

# Cancel events for manual kill (shared across executor instances)
_cancel_events: dict[UUID, asyncio.Event] = {}

# Strong references to background tasks (prevent GC before completion)
_background_tasks: set[asyncio.Task] = set()


@dataclass
class SubAgentResult:
    """Result of a sub-agent execution."""

    success: bool
    result: str = ""
    tokens_used: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    duration_seconds: float = 0.0
    session_id: str = ""  # Sub-agent session_id for token consolidation
    error: str | None = None
    task_id: str | None = None


class SubAgentExecutor:
    """Executes sub-agents through the full LIA graph.

    Supports two modes:
    - Synchronous: blocks until completion, returns result directly
    - Background: returns immediately with task_id, notifies on completion

    State management: The executor manages status transitions autonomously
    (READY → EXECUTING → READY/ERROR). Callers should NOT set status beforehand.

    Guard-rails:
    - Level 1: Static limits (recursion_limit, timeout, blocked tools)
    - Level 2: Mid-execution token monitoring via SubAgentTokenGuard
    - Level 3: Manual kill via cancel event, auto-disable after failures
    """

    async def execute(
        self,
        subagent: SubAgent,
        instruction: str,
        user_id: UUID,
        user_timezone: str = "Europe/Paris",
        user_language: str = "fr",
        db: Any = None,
        mode: str = "sync",
    ) -> SubAgentResult:
        """Execute a sub-agent synchronously.

        Manages full lifecycle: validation → status transition → execution → recording.

        Args:
            subagent: Sub-agent to execute.
            instruction: Task instruction for the sub-agent.
            user_id: Owner user ID.
            user_timezone: User timezone for context.
            user_language: User language for responses.
            db: Optional DB session for status updates. If None, status not managed.
            mode: Execution mode label for metrics ("sync" or "background").

        Returns:
            SubAgentResult with execution outcome.

        Raises:
            ResourceConflictError: If sub-agent is already executing.
            ValidationError: If sub-agent is disabled or budget exceeded.
        """
        self._validate_can_execute(subagent)
        await self._check_daily_budget(user_id)

        # Transition: READY → EXECUTING
        if db:
            await self._set_status(subagent, SubAgentStatus.EXECUTING.value, db)

        session_id = f"subagent_{subagent.id}_{uuid4().hex[:8]}"
        start_time = time.monotonic()

        # Register cancel event for manual kill
        cancel_event = asyncio.Event()
        _cancel_events[subagent.id] = cancel_event

        subagent_active_count.inc()
        subagent_spawned_total.labels(agent_name=subagent.name, mode=mode).inc()

        try:
            result = await self._run_with_guards(
                subagent=subagent,
                instruction=instruction,
                user_id=user_id,
                session_id=session_id,
                user_timezone=user_timezone,
                user_language=user_language,
                cancel_event=cancel_event,
            )

            duration = time.monotonic() - start_time
            result.duration_seconds = duration

            subagent_duration_seconds.labels(agent_name=subagent.name).observe(duration)
            if result.tokens_in:
                subagent_tokens_in_total.labels(agent_name=subagent.name).inc(result.tokens_in)
            if result.tokens_out:
                subagent_tokens_out_total.labels(agent_name=subagent.name).inc(result.tokens_out)

            await self._increment_daily_budget(user_id, result.tokens_used)

            # Transition: EXECUTING → READY/ERROR
            if db:
                new_status = (
                    SubAgentStatus.READY.value if result.success else SubAgentStatus.ERROR.value
                )
                await self._set_status(subagent, new_status, db)

            return result

        except Exception as exc:
            duration = time.monotonic() - start_time
            error_type = type(exc).__name__
            subagent_errors_total.labels(agent_name=subagent.name, error_type=error_type).inc()

            if db:
                await self._set_status(subagent, SubAgentStatus.ERROR.value, db)

            return SubAgentResult(
                success=False,
                error=f"{error_type}: {exc}",
                duration_seconds=duration,
            )

        finally:
            subagent_active_count.dec()
            _cancel_events.pop(subagent.id, None)

    async def execute_background(
        self,
        subagent: SubAgent,
        instruction: str,
        user_id: UUID,
        user_timezone: str = "Europe/Paris",
        user_language: str = "fr",
    ) -> str:
        """Launch sub-agent execution as a background task.

        Returns immediately with a task_id. On completion, notifies
        via NotificationDispatcher (SSE + FCM + archive).

        Args:
            subagent: Sub-agent to execute.
            instruction: Task instruction.
            user_id: Owner user ID.
            user_timezone: User timezone.
            user_language: User language.

        Returns:
            task_id string for tracking.

        Raises:
            ResourceConflictError: If sub-agent is already executing.
            ValidationError: If sub-agent is disabled or budget exceeded.
        """
        self._validate_can_execute(subagent)
        await self._check_daily_budget(user_id)

        task_id = f"subagent_bg_{subagent.id}_{uuid4().hex[:8]}"

        task = asyncio.create_task(
            self._background_worker(
                subagent_id=subagent.id,
                instruction=instruction,
                user_id=user_id,
                user_timezone=user_timezone,
                user_language=user_language,
                task_id=task_id,
            ),
            name=f"subagent_{subagent.name}_{task_id}",
        )
        # Keep strong reference to prevent GC before completion
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        logger.info(
            "subagent_background_launched",
            subagent_id=str(subagent.id),
            subagent_name=subagent.name,
            user_id=str(user_id),
            task_id=task_id,
        )

        return task_id

    # ========================================================================
    # Internal execution
    # ========================================================================

    async def _run_with_guards(
        self,
        subagent: SubAgent,
        instruction: str,
        user_id: UUID,
        session_id: str,
        user_timezone: str,
        user_language: str,
        cancel_event: asyncio.Event,
    ) -> SubAgentResult:
        """Run sub-agent with all guard-rails (timeout + token guard + cancel).

        Uses a simplified direct pipeline instead of the full LangGraph graph:
        1. Build minimal QueryIntelligence (no LLM call)
        2. SmartPlannerService.plan() → ExecutionPlan
        3. execute_plan_parallel() → tool results
        4. LLM synthesis → raw analytical text

        This bypasses router, semantic_validator, approval_gate, and response_node,
        eliminating ghost dependencies, replanning loops, and HITL triggers.
        """
        from src.domains.agents.dependencies import ToolDependencies
        from src.domains.chat.service import TrackingContext
        from src.infrastructure.database.session import get_db_context
        from src.infrastructure.observability.callbacks import TokenTrackingCallback

        # Token tracking for cost attribution
        tracker = TrackingContext(
            run_id=session_id,
            user_id=user_id,
            session_id=session_id,
            conversation_id=None,
            auto_commit=False,  # Explicit commit inside get_db_context block
        )
        token_callback = TokenTrackingCallback(tracker, session_id)

        # Tool dependencies (DB session must stay open during execution)
        async with get_db_context() as tool_db:
            tool_deps = ToolDependencies(db_session=tool_db)

            runnable_config = RunnableConfig(
                configurable={
                    "thread_id": str(uuid4()),
                    "user_id": user_id,
                    "langgraph_user_id": str(user_id),
                    "__deps": tool_deps,
                    "__user_message": instruction,
                    "user_timezone": user_timezone,
                    "user_language": user_language,
                },
                metadata={
                    "run_id": session_id,
                    "user_id": str(user_id),
                    "session_id": session_id,
                    "llm_type": "subagent",
                },
                callbacks=[token_callback],
            )

            async def _run_pipeline() -> str:
                """Execute the simplified sub-agent pipeline."""
                # Step 1: Analyze instruction (LLM-based domain detection)
                qi = await _analyze_instruction(
                    instruction=instruction,
                    expertise=subagent.system_prompt,
                    user_language=user_language,
                    config=runnable_config,
                )

                logger.info(
                    "subagent_pipeline_started",
                    subagent_name=subagent.name,
                    domains=qi.domains,
                    session_id=session_id,
                )

                # Step 2: Plan via SmartPlannerService
                from src.domains.agents.services.smart_planner_service import (
                    SmartPlannerService,
                )

                planner = SmartPlannerService()
                planning_result = await planner.plan(
                    intelligence=qi,
                    config=runnable_config,
                    exclude_tools=set(SUBAGENT_EXCLUDED_PLANNER_TOOLS),
                )

                if not planning_result.success or not planning_result.plan:
                    raise RuntimeError(f"Planning failed: {planning_result.error}")

                plan = planning_result.plan
                if not plan.steps:
                    raise RuntimeError("Planner generated empty plan (0 steps)")

                logger.info(
                    "subagent_planning_complete",
                    subagent_name=subagent.name,
                    step_count=len(plan.steps),
                    tools=[s.tool_name for s in plan.steps],
                    session_id=session_id,
                )

                if cancel_event.is_set():
                    raise asyncio.CancelledError(f"Sub-agent '{subagent.name}' cancelled")

                # Step 3: Execute tools via parallel executor
                from src.domains.agents.orchestration.parallel_executor import (
                    execute_plan_parallel,
                )

                exec_result = await execute_plan_parallel(
                    execution_plan=plan,
                    config=runnable_config,
                    run_id=session_id,
                )

                logger.info(
                    "subagent_execution_complete",
                    subagent_name=subagent.name,
                    completed_steps=len(exec_result.completed_steps),
                    session_id=session_id,
                )

                if cancel_event.is_set():
                    raise asyncio.CancelledError(f"Sub-agent '{subagent.name}' cancelled")

                # Step 4: Synthesize results via LLM
                content = await _synthesize_results(
                    instruction=instruction,
                    completed_steps=exec_result.completed_steps,
                    config=runnable_config,
                )

                return content

            # Race: pipeline execution vs timeout vs cancel
            pipeline_task = asyncio.create_task(_run_pipeline())
            cancel_task = asyncio.create_task(cancel_event.wait())

            done, pending = await asyncio.wait(
                [pipeline_task, cancel_task],
                timeout=subagent.timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel whatever didn't finish
            for p in pending:
                p.cancel()
                try:
                    await p
                except (asyncio.CancelledError, Exception):
                    logger.debug("sub_agent_task_cancel_suppressed")

            # Commit token tracking INSIDE the DB context so the parent
            # tool can read the MessageTokenSummary for consolidation.
            try:
                await tracker.commit()
            except Exception:
                logger.debug("sub_agent_token_commit_failed")

        # Collect token totals for Prometheus metrics (after commit)
        tracker_summary = tracker.get_summary()
        _tokens_in = tracker_summary.get("tokens_in", 0)
        _tokens_out = tracker_summary.get("tokens_out", 0)
        _tokens_used = _tokens_in + _tokens_out

        if cancel_task in done:
            subagent_killed_total.labels(agent_name=subagent.name, reason="manual").inc()
            return SubAgentResult(
                success=False,
                error=f"Sub-agent '{subagent.name}' manually cancelled",
                session_id=session_id,
            )

        if not done:
            subagent_killed_total.labels(agent_name=subagent.name, reason="timeout").inc()
            return SubAgentResult(
                success=False,
                error=(
                    f"Sub-agent '{subagent.name}' timed out " f"after {subagent.timeout_seconds}s"
                ),
                session_id=session_id,
            )

        # Pipeline completed — check for exceptions
        try:
            content = pipeline_task.result()
        except asyncio.CancelledError:
            return SubAgentResult(
                success=False,
                error=f"Sub-agent '{subagent.name}' was cancelled",
                session_id=session_id,
            )
        except Exception as exc:
            return SubAgentResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                session_id=session_id,
            )

        return SubAgentResult(
            success=True,
            result=content,
            tokens_used=_tokens_used,
            tokens_in=_tokens_in,
            tokens_out=_tokens_out,
            session_id=session_id,
        )

    async def _background_worker(
        self,
        subagent_id: UUID,
        instruction: str,
        user_id: UUID,
        user_timezone: str,
        user_language: str,
        task_id: str,
    ) -> None:
        """Background worker for async sub-agent execution.

        Manages its own DB session, status transitions, and notification dispatch.
        Pattern: scheduled_action_executor._execute_single_action().
        """
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            from src.domains.sub_agents.repository import SubAgentRepository
            from src.domains.sub_agents.service import SubAgentService

            repo = SubAgentRepository(db)
            service = SubAgentService(db)

            subagent = await repo.get_by_id(subagent_id)
            if not subagent:
                logger.error(
                    "subagent_background_not_found",
                    subagent_id=str(subagent_id),
                )
                return

            try:
                # execute() manages status transitions via db param
                result = await self.execute(
                    subagent=subagent,
                    instruction=instruction,
                    user_id=user_id,
                    user_timezone=user_timezone,
                    user_language=user_language,
                    db=db,
                    mode="background",
                )

                # Generate summary (first 200 chars)
                summary = (
                    result.result[:200] + "..."
                    if result.result and len(result.result) > 200
                    else result.result or ""
                )

                # Record execution result
                await service.record_execution(
                    subagent_id=subagent_id,
                    success=result.success,
                    summary=summary if result.success else None,
                    error=result.error,
                )
                await db.commit()

                # Notify user
                await self._notify_completion(
                    user_id=user_id,
                    subagent=subagent,
                    result=result,
                    task_id=task_id,
                    db=db,
                )

            except Exception as exc:
                logger.error(
                    "subagent_background_error",
                    subagent_id=str(subagent_id),
                    error=f"{type(exc).__name__}: {exc}",
                    task_id=task_id,
                )
                try:
                    await service.record_execution(
                        subagent_id=subagent_id,
                        success=False,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    await db.commit()
                except Exception:
                    logger.error(
                        "subagent_background_record_failed",
                        subagent_id=str(subagent_id),
                    )

    # ========================================================================
    # Pre-execution validation
    # ========================================================================

    @staticmethod
    def _validate_can_execute(subagent: SubAgent) -> None:
        """Validate sub-agent is in a valid state for execution.

        Checks enabled status and concurrency (not already executing).

        Raises:
            ValidationError: If sub-agent is disabled.
            ResourceConflictError: If sub-agent is already executing.
        """
        if not subagent.is_enabled:
            raise ValidationError(
                f"Sub-agent '{subagent.name}' is disabled",
                subagent_id=str(subagent.id),
            )

        if subagent.status == SubAgentStatus.EXECUTING.value:
            raise ResourceConflictError(
                "sub_agent",
                f"Sub-agent '{subagent.name}' is already executing. " "Please wait for completion.",
            )

    # ========================================================================
    # Status management
    # ========================================================================

    @staticmethod
    async def _set_status(subagent: SubAgent, status: str, db: Any) -> None:
        """Update sub-agent status in the database.

        Args:
            subagent: Sub-agent ORM instance.
            status: New status value.
            db: AsyncSession for the update.
        """
        subagent.status = status
        await db.flush()

    # ========================================================================
    # Daily budget (Redis)
    # ========================================================================

    @staticmethod
    async def _check_daily_budget(user_id: UUID) -> None:
        """Check if user's daily sub-agent token budget is exceeded.

        Uses Redis GET for atomic, O(1) budget check.

        Raises:
            ValidationError: If daily budget is exceeded.
        """
        max_daily = getattr(settings, "subagent_max_total_tokens_per_day", 500000)

        try:
            from src.infrastructure.cache.redis import get_redis_cache

            redis = await get_redis_cache()
            key = f"{SUBAGENT_DAILY_BUDGET_KEY_PREFIX}{user_id}"
            current = await redis.get(key)

            if current and int(current) >= max_daily:
                raise ValidationError(
                    f"Daily sub-agent token budget exceeded "
                    f"({int(current)}/{max_daily} tokens)",
                    user_id=str(user_id),
                )
        except ValidationError:
            raise
        except Exception as exc:
            # Redis failure should not block execution — log and continue
            logger.warning(
                "subagent_daily_budget_check_failed",
                user_id=str(user_id),
                error=str(exc),
            )

    @staticmethod
    async def _increment_daily_budget(user_id: UUID, tokens: int) -> None:
        """Increment the daily token budget counter in Redis.

        Uses INCRBY (atomic) + TTL 86400s (reset at midnight UTC).
        """
        if tokens <= 0:
            return

        try:
            from src.domains.sub_agents.constants import (
                SUBAGENT_DAILY_BUDGET_TTL_SECONDS,
            )
            from src.infrastructure.cache.redis import get_redis_cache

            redis = await get_redis_cache()
            key = f"{SUBAGENT_DAILY_BUDGET_KEY_PREFIX}{user_id}"

            pipe = redis.pipeline()
            pipe.incrby(key, tokens)
            pipe.expire(key, SUBAGENT_DAILY_BUDGET_TTL_SECONDS)
            await pipe.execute()
        except Exception as exc:
            # Redis failure should not break execution — log and continue
            logger.warning(
                "subagent_daily_budget_increment_failed",
                user_id=str(user_id),
                tokens=tokens,
                error=str(exc),
            )

    # ========================================================================
    # Notification
    # ========================================================================

    @staticmethod
    async def _notify_completion(
        user_id: UUID,
        subagent: SubAgent,
        result: SubAgentResult,
        task_id: str,
        db: Any,
    ) -> None:
        """Notify user of background sub-agent completion via SSE/FCM/archive."""
        try:
            from src.infrastructure.proactive.notification import (
                send_notification_to_channels,
            )

            status_label = "completed" if result.success else "failed"
            body = result.result[:150] + "..." if result.result else result.error or ""

            await send_notification_to_channels(
                user_id=user_id,
                title=f"Sub-agent '{subagent.name}' {status_label}",
                body=body,
                task_type="subagent_result",
                target_id=task_id,
                db=db,
            )
        except Exception as exc:
            logger.warning(
                "subagent_notification_failed",
                user_id=str(user_id),
                subagent_name=subagent.name,
                task_id=task_id,
                error=str(exc),
            )

    # ========================================================================
    # Stale recovery (called by APScheduler job)
    # ========================================================================

    @staticmethod
    async def recover_stale_subagents() -> int:
        """Reset sub-agents stuck in 'executing' status.

        Called periodically by APScheduler. Resets zombie sub-agents
        that exceeded their timeout + 60s margin.

        Returns:
            Number of recovered sub-agents.
        """
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            from src.domains.sub_agents.repository import SubAgentRepository
            from src.domains.sub_agents.service import SubAgentService

            repo = SubAgentRepository(db)
            service = SubAgentService(db)

            stale = await repo.get_stale_executing()
            if not stale:
                return 0

            for subagent in stale:
                await service.record_execution(
                    subagent_id=subagent.id,
                    success=False,
                    error="Execution timed out (stale recovery)",
                )
                subagent_killed_total.labels(
                    agent_name=subagent.name, reason="stale_recovery"
                ).inc()

                logger.warning(
                    "subagent_stale_recovered",
                    subagent_id=str(subagent.id),
                    subagent_name=subagent.name,
                )

            await db.commit()

            logger.info(
                "subagent_stale_recovery_completed",
                recovered_count=len(stale),
            )

            return len(stale)

    # ========================================================================
    # Manual kill
    # ========================================================================

    @staticmethod
    def cancel_execution(subagent_id: UUID) -> bool:
        """Signal cancellation for a running sub-agent.

        Returns True if cancel event was set, False if no running execution found.
        """
        event = _cancel_events.get(subagent_id)
        if event and not event.is_set():
            event.set()
            logger.info(
                "subagent_cancel_requested",
                subagent_id=str(subagent_id),
            )
            return True
        return False


# ============================================================================
# Module-level helpers for the direct sub-agent pipeline
# ============================================================================


async def _analyze_instruction(
    instruction: str,
    expertise: str,
    user_language: str,
    config: RunnableConfig,
) -> QueryIntelligence:
    """Analyze sub-agent instruction to build proper QueryIntelligence.

    Uses the same QueryAnalyzerService as the main assistant's router
    for accurate domain detection and intent analysis. This ensures
    sub-agents get the correct tool catalogue from the planner.

    Falls back to a minimal QueryIntelligence with ["web_search"]
    if the LLM analysis fails (graceful degradation).

    Args:
        instruction: Task instruction from the parent planner.
        expertise: Sub-agent expertise description (system_prompt).
        user_language: User's language code.
        config: RunnableConfig for LLM callback propagation.

    Returns:
        QueryIntelligence with LLM-detected domains and intent.
    """
    from src.domains.agents.analysis.query_intelligence import (
        QueryIntelligence,
        UserGoal,
    )

    # Combine instruction + expertise for richer context
    analysis_query = f"{expertise}\n\n{instruction}"

    try:
        from src.domains.agents.services.query_analyzer_service import (
            analyze_query,
        )

        analysis = await analyze_query(
            query=analysis_query,
            base_config=config,
        )

        domains = analysis.domains
        if not domains:
            domains = ["web_search"]

        return QueryIntelligence(
            original_query=instruction,
            english_query=analysis.english_query or instruction,
            immediate_intent=analysis.intent if analysis.intent != "conversation" else "search",
            immediate_confidence=analysis.confidence,
            user_goal=UserGoal.FIND_INFORMATION,
            goal_reasoning="Sub-agent delegated task",
            domains=domains,
            primary_domain=domains[0],
            route_to="planner",
            turn_type="ACTION",
            user_language=user_language,
            is_mutation_intent=False,
            has_cardinality_risk=False,
            for_each_detected=analysis.for_each_detected,
            for_each_collection_key=analysis.for_each_collection_key,
            cardinality_magnitude=analysis.cardinality_magnitude,
        )

    except Exception as exc:
        logger.warning(
            "subagent_analyze_instruction_failed",
            error=f"{type(exc).__name__}: {exc}",
        )
        # Fallback: web_search domain (broadest tool access)
        return QueryIntelligence(
            original_query=instruction,
            english_query=instruction,
            immediate_intent="search",
            immediate_confidence=0.8,
            user_goal=UserGoal.FIND_INFORMATION,
            goal_reasoning="Sub-agent delegated task (fallback — analysis failed)",
            domains=["web_search"],
            primary_domain="web_search",
            route_to="planner",
            turn_type="ACTION",
            user_language=user_language,
            is_mutation_intent=False,
            has_cardinality_risk=False,
        )


async def _synthesize_results(
    instruction: str,
    completed_steps: dict[str, dict[str, Any]],
    config: RunnableConfig,
) -> str:
    """Synthesize tool execution results into raw analytical text.

    Uses the "subagent" LLM type for a single synthesis call.
    Falls back to raw concatenation if LLM fails.

    Args:
        instruction: Original task instruction.
        completed_steps: Step results from execute_plan_parallel().
        config: RunnableConfig with callbacks for token tracking.

    Returns:
        Synthesized text (consumed by parent assistant, not shown to user).
    """
    formatted = _format_completed_steps(completed_steps)

    # Short-circuit: if no results, return early
    if not completed_steps:
        return "No tool results were produced."

    try:
        from langchain_core.messages import HumanMessage

        from src.domains.agents.prompts.prompt_loader import load_prompt
        from src.infrastructure.llm.factory import get_llm

        llm = get_llm("subagent")
        prompt_template = load_prompt(SUBAGENT_SYNTHESIS_PROMPT_NAME)

        prompt = prompt_template.replace("{instruction}", instruction).replace(
            "{results}", formatted
        )

        # Use HumanMessage (not SystemMessage) for Anthropic compatibility.
        # Anthropic API requires at least one user/human message.
        response = await llm.ainvoke(
            [HumanMessage(content=prompt)],
            config=config,
        )
        content = response.content
        return content if isinstance(content, str) else formatted
    except Exception as exc:
        logger.warning(
            "subagent_synthesis_llm_failed",
            error=f"{type(exc).__name__}: {exc}",
        )
        # Fallback: return raw formatted results
        return formatted


def _format_completed_steps(completed_steps: dict[str, dict[str, Any]]) -> str:
    """Format parallel executor results into readable text blocks.

    The parallel executor stores results as:
    - Success + structured_data: the structured dict directly (e.g., {"synthesis": ...})
    - Success + result data: result["data"] or the full result dict
    - Success + no data: {"success": True}
    - Error: {"success": False, "error": "..."}

    Args:
        completed_steps: Mapping of step_id → result dict from executor.

    Returns:
        Multi-line text with one block per step.
    """
    if not completed_steps:
        return "(no results)"

    parts: list[str] = []
    for step_id, data in completed_steps.items():
        if not isinstance(data, dict):
            parts.append(f"[{step_id}] {str(data)[:2000]}")
            continue

        # Error case: {"success": False, "error": "..."}
        if data.get("success") is False and data.get("error"):
            parts.append(f"[{step_id}] ERROR: {data['error']}")
            continue

        # Success case: try to extract the most readable field
        text = (
            data.get("synthesis")
            or data.get("analysis")
            or data.get("content")
            or data.get("summary")
            or data.get("text")
        )
        if text and isinstance(text, str):
            parts.append(f"[{step_id}] {text[:3000]}")
        elif data.get("success") is True and len(data) == 1:
            # Empty success: {"success": True}
            parts.append(f"[{step_id}] (completed, no data)")
        else:
            parts.append(f"[{step_id}] {json.dumps(data, ensure_ascii=False, default=str)[:2000]}")

    return "\n\n".join(parts)
