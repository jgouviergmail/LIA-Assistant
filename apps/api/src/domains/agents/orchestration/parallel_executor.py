"""
Parallel Execution Module (Phase 5.2B-asyncio).

This module implements TRUE parallel execution using Python's native asyncio.gather(),
replacing the broken LangGraph Command+Send pattern (GitHub issues #3329, #3240, #1406).

Architecture (asyncio Pattern):
    Task Orchestrator
        ↓ execute_plan_parallel()
    Parallel Executor (this module)
        ↓ asyncio.gather([step1, step2, step3])
    _execute_single_step_async() ← Executes steps in parallel
        ↓ Returns StepResults
    Merge results → Calculate next wave
        ↓
    If incomplete:
        → asyncio.gather(next wave)
    If complete:
        → Return all results

Responsibilities:
- Execute ExecutionPlan with true parallel execution
- Wave-by-wave execution based on dependency graph
- TOOL and CONDITIONAL step execution
- Reference resolution ($steps.X.field)
- CONDITIONAL branching (on_success/on_fail routing)
- Error handling (failed steps don't crash execution)

Key Design Decisions:
1. **Native asyncio**: No LangGraph framework coupling
2. **Wave-based**: Respect dependencies via DependencyGraph
3. **Immutable Results**: StepResult frozen Pydantic models
4. **Reuse**: Copy-paste from step_executor_node.py and wave_aggregator_node.py
5. **Thread Safety**: No shared mutable state

Advantages over LangGraph Map-Reduce:
- Works reliably (no framework bugs)
- Simpler code (~500 lines vs ~1500 lines)
- Less framework coupling
- Better performance (no graph overhead)
- Easier debugging

Integration:
- Called by task_orchestrator_node._handle_execution_plan()
- Returns completed_steps dict for response_node

Best Practices (2025):
- Type hints everywhere
- Structured logging
- Comprehensive error handling
- Minimal dependencies

Phase 5.3 Extensions:
- HITL support (await user approval)
- Dynamic plan modification
- Advanced retry strategies

Example Usage:
    >>> plan = ExecutionPlan(steps=[...])
    >>> completed_steps = await execute_plan_parallel(
    ...     execution_plan=plan,
    ...     config=config,
    ... )
    >>> # Returns: {"step1": {...}, "step2": {...}}

References:
    - dependency_graph.py: Wave calculation
    - step_executor_node.py: Original worker implementation (copied from)
    - wave_aggregator_node.py: Original reducer implementation (copied from)
    - plan_executor.py: Legacy sequential executor
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import TYPE_CHECKING, Any

import structlog
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict

from src.core.constants import (
    DEFAULT_TOOL_TIMEOUT_SECONDS,
    HTTP_TIMEOUT_CONDITIONAL_EVAL,
    MAX_TOOL_TIMEOUT_SECONDS,
)
from src.core.field_names import (
    FIELD_CORRELATED_TO,
    FIELD_CORRELATION_PARENT_ID,
    FIELD_ERROR_CODE,
    FIELD_METADATA,
    FIELD_NODE_NAME,
    FIELD_REGISTRY_ID,
    FIELD_RESULT,
    FIELD_STEP_ID,
    FIELD_TOOL_NAME,
    FIELD_TURN_ID,
    FIELD_USER_ID,
)
from src.domains.agents.constants import TOOL_LOCAL_QUERY_ENGINE
from src.domains.agents.orchestration.condition_evaluator import (
    ConditionEvaluator,
    ReferenceResolver,
)
from src.domains.agents.orchestration.dependency_graph import DependencyGraph
from src.domains.agents.orchestration.for_each_utils import (
    is_for_each_ready_for_expansion,
)

# Issue #41: Jinja2 template evaluation for conditional parameters
from src.domains.agents.orchestration.jinja_evaluator import (
    EmptyResultError,
    JinjaTemplateEvaluator,
)
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType

# 2026-01: Text compaction for token optimization (post-Jinja evaluation)
from src.domains.agents.orchestration.text_compaction import compact_text_params
from src.domains.agents.services.hitl.scope_detector import detect_for_each_scope
from src.domains.agents.tools.common import ToolErrorCode

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


# ============================================================================
# Data Registry LOT 5.2: Execution Result with Registry
# ============================================================================


class PendingDraftInfo(BaseModel):
    """
    Information about a draft requiring user confirmation.

    Data Registry LOT 4.3: Captures draft details for HITL draft_critique flow.

    When a tool creates a draft (email, event, contact) with requires_confirmation=True,
    this structure holds the information needed by draft_critique_node to:
    1. Generate a contextual review question
    2. Present options to user (confirm/edit/cancel)
    3. Process user decision

    Attributes:
        draft_id: Unique draft identifier (e.g., "draft_abc123")
        draft_type: Type of draft ("email", "event", "contact")
        draft_content: Draft content dict (to, subject, body for email, etc.)
        draft_summary: Pre-generated summary for LLM context
        registry_ids: Data registry IDs associated with this draft
        tool_name: Name of the tool that created the draft
        step_id: ExecutionPlan step that created the draft
    """

    draft_id: str
    draft_type: str
    draft_content: dict[str, Any]
    draft_summary: str
    registry_ids: list[str]
    tool_name: str | None = None
    step_id: str | None = None


class ParallelExecutionResult(BaseModel):
    """
    Result of parallel plan execution with data registry support.

    Data Registry LOT 5.2: Contains both step results and accumulated registry items.
    Data Registry LOT 4.3: Contains pending draft info for HITL draft_critique flow.

    Attributes:
        completed_steps: Dict mapping step_id -> result data (for response_node)
        registry: Data registry items accumulated from all registry-enabled tools
                  Keys are registry IDs (e.g., "contact_abc123")
                  Values are serialized RegistryItem dicts
        pending_draft: First draft requiring confirmation (backwards compat, single-draft path)
                      None if no draft requires confirmation
        pending_drafts: All drafts requiring confirmation (batch path for FOR_EACH)
                       Empty list if no drafts require confirmation
    """

    completed_steps: dict[str, dict[str, Any]]
    registry: dict[str, Any]  # Serialized RegistryItem dicts
    pending_draft: PendingDraftInfo | None = None  # Data Registry LOT 4.3
    pending_drafts: list[PendingDraftInfo] = []  # Batch support for FOR_EACH


# Issue #41: Module-level Jinja2 evaluator instance (thread-safe, reusable)
# Issue #60 Fix: Use configurable max_recursion_depth instead of hardcoded 10
from src.core.config import get_settings  # noqa: E402

_settings = get_settings()
_jinja_evaluator = JinjaTemplateEvaluator(max_recursion_depth=_settings.jinja_max_recursion_depth)

# Issue #41: Required parameters per tool (for empty result detection)
# Architecture: Supports two validation modes:
#   - list[str]: AND logic - ALL parameters must be present (e.g., ["to", "subject", "body"])
#   - {"one_of": [...]}: OR logic - AT LEAST ONE parameter must be present
#
# v2.0 Unified Architecture (2026-01): Unified tools replace search/list/details
REQUIRED_PARAMS_BY_TOOL: dict[str, list[str] | dict[str, list[str]]] = {
    # Gmail tools (v2.0 unified)
    "get_emails_tool": [],  # Unified: query or message_id(s) - all optional
    "send_email_tool": ["to"],  # subject/body optional when content_instruction provided
    # Contacts tools (v2.0 unified)
    "get_contacts_tool": [],  # Unified: query or resource_name(s) - all optional
    # Calendar tools (v2.0 unified)
    "get_events_tool": [],  # Unified: query or event_id(s) - all optional
    "list_calendars_tool": [],  # Container metadata - all optional
    "create_event_tool": ["summary", "start_datetime", "end_datetime"],
    "update_event_tool": ["event_id"],
    "delete_event_tool": ["event_id"],
    # Drive tools (v2.0 unified)
    "get_files_tool": [],  # Unified: query or file_id(s) - all optional
    # Tasks tools (v2.0 unified)
    "get_tasks_tool": [],  # Unified: task_id(s) or filter - all optional
    "list_task_lists_tool": [],  # Container metadata - all optional
    "create_task_tool": ["title"],
    "complete_task_tool": ["task_id"],
    # Weather tools - location is optional (auto-detection via geolocation/home)
    "get_current_weather_tool": [],
    "get_weather_forecast_tool": [],
    "get_hourly_forecast_tool": [],
    # Wikipedia tools
    "search_wikipedia_tool": ["query"],
    "get_wikipedia_summary_tool": ["title"],
    "get_wikipedia_article_tool": ["title"],
    "get_wikipedia_related_tool": ["title"],
    # Context tools
    "resolve_reference_tool": [],
    "get_context_list_tool": [],
    "set_current_item_tool": [],
    "get_context_state_tool": [],
    "list_active_domains_tool": [],
    # INTELLIA LocalQueryEngine
    "local_query_engine_tool": ["query"],
    # Perplexity tools
    "perplexity_search_tool": ["query"],
    "perplexity_ask_tool": ["question"],
    # Places tools (v2.0 unified)
    "get_places_tool": [],  # Unified: query or place_id(s) - all optional
}


def _is_param_empty(value: Any) -> bool:
    """Check if a parameter value is empty (None, empty string, or empty list)."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


def _validate_required_params(
    tool_name: str,
    resolved_args: dict[str, Any],
) -> tuple[bool, str | None]:
    """
    Validate required parameters with AND/OR support.

    Architecture:
    - list[str]: AND logic - ALL listed parameters must be present and non-empty
    - {"one_of": [...]}: OR logic - AT LEAST ONE of the listed parameters must be present

    Args:
        tool_name: Name of the tool being executed
        resolved_args: Dictionary of resolved parameter values

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    required_config = REQUIRED_PARAMS_BY_TOOL.get(tool_name, [])

    # Empty list = no required params
    if not required_config:
        return True, None

    # List = AND logic (all required) - backward-compatible
    if isinstance(required_config, list):
        for param_name in required_config:
            if _is_param_empty(resolved_args.get(param_name)):
                error_msg = (
                    f"Required parameter '{param_name}' is empty after template evaluation. "
                    f"This usually means the Jinja template condition was not met "
                    f"(e.g., no groups with count > 1, or no matching items)."
                )
                return False, error_msg
        return True, None

    # Dict with "one_of" = OR logic (at least one required)
    if isinstance(required_config, dict) and "one_of" in required_config:
        alternatives = required_config["one_of"]
        for param_name in alternatives:
            if not _is_param_empty(resolved_args.get(param_name)):
                return True, None  # Found at least one valid parameter

        # None of the alternatives provided
        error_msg = (
            f"At least one of {alternatives} must be provided for '{tool_name}'. "
            f"All alternatives are empty after template evaluation. "
            f"Received args: {list(resolved_args.keys())}"
        )
        return False, error_msg

    # Unknown config format - treat as valid (fail-safe)
    logger.warning(
        "unknown_required_params_config",
        tool_name=tool_name,
        config_type=type(required_config).__name__,
    )
    return True, None


def _get_jinja_required_params(tool_name: str) -> list[str]:
    """
    Get the list of required params for Jinja template evaluation.

    Architecture (2026-01-02):
    The jinja_evaluator validates that templates don't evaluate to empty for required params.
    However, it evaluates ONE template at a time, so it cannot validate OR logic (one_of).

    For AND logic (list): Return the list - Jinja should fail if ANY required param is empty.
    For OR logic (one_of): Return [] - Jinja cannot validate, real validation is done later
                           by _validate_required_params after all templates are evaluated.

    This ensures:
    1. AND logic: Early failure in Jinja evaluation (same as before)
    2. OR logic: No Jinja failure, validation happens in _validate_required_params

    Args:
        tool_name: Name of the tool

    Returns:
        List of param names that should be treated as required by Jinja evaluator.
        Empty list for one_of configs or unknown tools.
    """
    required_config = REQUIRED_PARAMS_BY_TOOL.get(tool_name, [])

    # List = AND logic - return as-is for Jinja validation
    if isinstance(required_config, list):
        return required_config

    # Dict with one_of = OR logic - return empty, Jinja cannot validate OR
    # Real validation done by _validate_required_params after all templates evaluated
    if isinstance(required_config, dict) and "one_of" in required_config:
        return []

    # Unknown format - return empty (safe default)
    return []


# ============================================================================
# StreamWriter for Non-Graph Tool Execution (Session 22)
# ============================================================================


class NullStreamWriter:
    """
    Minimal StreamWriter for non-graph tool execution.

    LangGraph v1.0 Best Practice:
    - StreamWriter is a Callable protocol (abstract)
    - Cannot be instantiated with StreamWriter(None, None)
    - Must create concrete subclass implementing __call__

    Used when executing tools outside graph context where streaming
    is not available/needed. Silently discards stream writes.

    Architecture:
    - Implements __call__ to satisfy StreamWriter protocol
    - No-op implementation (discards all writes)
    - Thread-safe (no shared state)

    Session 22: Moved to module level from _execute_tool() for reusability.
    """

    def __call__(self, chunk: Any) -> None:
        """Ignore stream writes outside graph context."""
        pass


# ============================================================================
# Tool Registry (Delegating Wrapper)
# ============================================================================


class ToolRegistry:
    """
    Wrapper around the central tool registry.

    Delegates all operations to src.domains.agents.tools.tool_registry,
    which uses @registered_tool decorators for auto-registration.

    This class maintains API compatibility with existing code while
    eliminating hardcoded tool lists.

    Architecture:
    - Delegates to central tool_registry module
    - Tools auto-register via @registered_tool decorator
    - No hardcoded imports or tool lists
    - Thread-safe via central registry

    Usage:
        >>> registry = ToolRegistry.get_instance()
        >>> tool = registry.get_tool("get_contacts_tool")
        >>> result = await tool.ainvoke(args, config)

    Adding new tools:
        1. Create tool with @registered_tool decorator
        2. That's it! Tool is automatically available everywhere.
    """

    _instance: ToolRegistry | None = None
    _lock: threading.RLock = threading.RLock()

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        """Get or create singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        """Initialize registry (ensures tools are loaded)."""
        from src.domains.agents.tools.tool_registry import ensure_tools_loaded

        ensure_tools_loaded()

    def get_tool(self, tool_name: str) -> Any:
        """
        Get tool instance by name.

        Args:
            tool_name: Tool name (e.g., "get_contacts_tool")

        Returns:
            LangChain tool instance

        Raises:
            KeyError: If tool not found
        """
        from src.domains.agents.tools.tool_registry import get_tool_strict

        return get_tool_strict(tool_name)

    def has_tool(self, tool_name: str) -> bool:
        """Check if tool exists in registry."""
        from src.domains.agents.tools.tool_registry import has_tool

        return has_tool(tool_name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        from src.domains.agents.tools.tool_registry import list_tool_names

        return list_tool_names()


# ============================================================================
# Step Result Schema
# ============================================================================


class StepResult(BaseModel):
    """
    Result of executing a single step.

    Copied from step_executor_node.StepResult.

    Data Registry LOT 5.2: Added registry_updates field for registry-enabled tools.
    INTELLIPLANNER B+: Added structured_data field for Jinja2 template access.

    Attributes:
        step_id: Unique step identifier (e.g., "search", "validate")
        step_type: Type of step executed (TOOL, CONDITIONAL)
        tool_name: Name of tool executed (None for CONDITIONAL)
        args: Resolved arguments used (None for CONDITIONAL)
        result: Result returned by tool (dict ToolResponse)
        condition_result: Result of condition evaluation (bool, for CONDITIONAL)
        success: True if step succeeded
        error: Error message if failure
        error_code: Error code if failure
        execution_time_ms: Execution time in milliseconds
        hitl_approved: True if HITL approved (None if no HITL)
        wave_id: Wave number this step belonged to (for metrics)
        registry_updates: Data registry items from StandardToolOutput (None if legacy tool)
        structured_data: Queryable data for Jinja2 templates (None if legacy tool)

    Examples:
        >>> # TOOL step result with data registry
        >>> result = StepResult(
        ...     step_id="search",
        ...     step_type=StepType.TOOL,
        ...     tool_name="get_contacts_tool",
        ...     args={"query": "John"},
        ...     result={"success": True, "data": {"contacts": [...]}},
        ...     success=True,
        ...     execution_time_ms=250,
        ...     wave_id=0,
        ...     registry_updates={"contact_abc": {...}}
        ... )

        >>> # CONDITIONAL step result
        >>> result = StepResult(
        ...     step_id="validate_search",
        ...     step_type=StepType.CONDITIONAL,
        ...     condition_result=True,
        ...     success=True,
        ...     execution_time_ms=5,
        ...     wave_id=1
        ... )
    """

    step_id: str
    step_type: StepType
    tool_name: str | None = None
    args: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    condition_result: bool | None = None
    success: bool
    error: str | None = None
    error_code: ToolErrorCode | None = None
    execution_time_ms: int = 0
    hitl_approved: bool | None = None
    wave_id: int | None = None
    # Data Registry LOT 5.2: Registry updates from StandardToolOutput
    registry_updates: dict[str, Any] | None = None
    # Data Registry LOT 4.3: Draft info if tool requires confirmation
    draft_info: dict[str, Any] | None = None
    # INTELLIPLANNER B+: Structured data for Jinja2 templates
    structured_data: dict[str, Any] | None = None

    model_config = ConfigDict(frozen=True)  # Immutable after creation (performance + safety)


# ============================================================================
# Reference Resolution & Condition Evaluation
# ============================================================================
#
# REFACTORED (2025-11-16 - Session 15):
# ReferenceResolver and ConditionEvaluator have been extracted to a shared module:
#   src/domains/agents/orchestration/condition_evaluator.py
#
# This eliminates 194 lines of duplication between parallel_executor.py and
# step_executor_node.py (Phase 1 - Code Duplication Refactoring).
#
# Both classes are now imported at the top of this file.


# ============================================================================
# Context Loading (Phase 8.5)
# ============================================================================


async def _load_execution_contexts(
    config: RunnableConfig,
    store: Any,
    run_id: str,
) -> dict[str, Any]:
    """
    Load all active contexts from store for context.X reference resolution.

    Phase 8.5: Enables Planner to reference previous tool results like
    context.contacts[0].resource_name in step parameters.

    Args:
        config: RunnableConfig with user_id, thread_id
        store: AsyncPostgresStore for context persistence
        run_id: Run ID for logging

    Returns:
        dict mapping domain_name -> list of context items
        Example: {"contacts": [item1_dict, item2_dict, ...]}

    Algorithm:
        1. Extract user_id and thread_id from config
        2. Load all active domains for this session
        3. For each domain, load context list (items)
        4. Build context dict {domain_name: items}

    Error Handling:
        - Missing user_id/thread_id: Return empty dict (non-blocking)
        - Failed domain load: Skip domain with warning (non-blocking)
        - Context resolution is optional enhancement

    Best Practices (2025):
        - Non-blocking: Failures don't crash execution
        - Comprehensive logging for debugging
        - Empty dict fallback (graceful degradation)
    """
    context: dict[str, Any] = {}

    try:
        user_id = config.get("configurable", {}).get(FIELD_USER_ID)
        thread_id = config.get("configurable", {}).get("thread_id")

        logger.info(
            "parallel_executor_context_loading_attempt",
            run_id=run_id,
            has_user_id=user_id is not None,
            has_thread_id=thread_id is not None,
            has_store=store is not None,
        )

        if not (user_id and thread_id and store):
            return context

        from src.domains.agents.context.manager import ToolContextManager

        context_manager = ToolContextManager()

        # Load all active domains for this session
        active_domains = await context_manager.list_active_domains(
            user_id=str(user_id), session_id=str(thread_id), store=store
        )

        logger.info(
            "parallel_executor_active_domains_loaded",
            run_id=run_id,
            active_domains_count=len(active_domains),
            domains=[d["domain"] for d in active_domains],
        )

        # Load data for each active domain into context dict
        for domain_info in active_domains:
            domain_name = domain_info["domain"]
            try:
                # Get list of items from context store
                context_list = await context_manager.get_list(
                    user_id=str(user_id),
                    session_id=str(thread_id),
                    domain=domain_name,
                    store=store,
                )

                if context_list and context_list.items:
                    # Convert ToolContextList to list for reference resolution
                    # Format: context["contacts"] = [item1_dict, item2_dict, ...]
                    # This allows $context.contacts.0, $context.contacts.1, etc.
                    context[domain_name] = context_list.items
                    logger.info(
                        "parallel_executor_domain_context_loaded",
                        run_id=run_id,
                        domain=domain_name,
                        items_count=len(context_list.items),
                    )
                else:
                    logger.warning(
                        "parallel_executor_domain_context_empty",
                        run_id=run_id,
                        domain=domain_name,
                    )
            except (ValueError, KeyError, RuntimeError, AttributeError) as e:
                logger.warning(
                    "context_load_failed_for_domain",
                    domain=domain_name,
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True,
                )

        logger.info(
            "parallel_executor_context_loaded",
            run_id=run_id,
            context_keys=list(context.keys()),
            total_contexts=len(context),
        )

    except (ValueError, KeyError, RuntimeError, AttributeError) as e:
        # Non-blocking: context resolution is optional enhancement
        logger.warning(
            "parallel_executor_context_load_failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )

    return context


# ============================================================================
# Plan Completion Checking
# ============================================================================


def _check_plan_completion(
    execution_plan: ExecutionPlan,
    completed_steps: dict[str, dict[str, Any]],
    run_id: str,
) -> tuple[bool, bool]:
    """
    Check if execution plan is complete or deadlocked.

    Args:
        execution_plan: The execution plan being executed
        completed_steps: Steps completed so far
        run_id: Run ID for logging

    Returns:
        Tuple of (is_complete, is_deadlocked)
        - is_complete: True if all required steps completed
        - is_deadlocked: True if remaining steps cannot execute (dependency deadlock)

    Algorithm:
        1. Calculate all step IDs in plan
        2. Identify skipped steps (CONDITIONAL branching)
        3. Calculate required steps = all steps - skipped steps
        4. Check if completed >= required (complete)
        5. If not complete, log deadlock with remaining steps

    Best Practices (2025):
        - Clear separation of concerns (plan completion logic)
        - Comprehensive error logging for debugging deadlocks
        - Return tuple for explicit state communication
    """
    all_step_ids = {step.step_id for step in execution_plan.steps}
    skipped_steps = _identify_skipped_steps(execution_plan, completed_steps)
    required_steps = all_step_ids - skipped_steps

    # Dashboard 15 LangGraph plan execution metrics
    try:
        from src.infrastructure.observability.metrics_agents import (
            langgraph_plan_execution_efficiency,
            langgraph_plan_steps_skipped_total,
        )

        plan_type = getattr(execution_plan, "execution_mode", "pipeline") or "pipeline"
        executed = len(set(completed_steps.keys()) & required_steps)
        total = len(all_step_ids)
        if total > 0:
            langgraph_plan_execution_efficiency.labels(plan_type=plan_type).observe(
                executed / total
            )
        for _skipped_id in skipped_steps:
            langgraph_plan_steps_skipped_total.labels(
                plan_type=plan_type, skip_reason="conditional_branch"
            ).inc()
    except Exception:
        pass

    if set(completed_steps.keys()) >= required_steps:
        # Plan complete: all required steps executed
        return True, False

    # Plan incomplete: check if deadlocked
    remaining = required_steps - set(completed_steps.keys())
    logger.error(
        "parallel_execution_deadlock",
        run_id=run_id,
        plan_id=execution_plan.plan_id,
        completed=list(completed_steps.keys()),
        remaining=list(remaining),
    )
    return False, True


# ============================================================================
# Wave Execution
# ============================================================================


async def _execute_wave_parallel(
    next_wave: set[str],
    steps_by_id: dict[str, ExecutionStep],
    completed_steps: dict[str, dict[str, Any]],
    execution_plan: ExecutionPlan,
    config: RunnableConfig,
    store: Any,
    context: dict[str, Any],
    current_wave_id: int,
    run_id: str,
    accumulated_registry: dict[str, Any] | None = None,
    accumulated_drafts: list[dict[str, Any]] | None = None,
    current_turn_touched_ids: set[str] | None = None,
    turn_id: int | None = None,
) -> list[StepResult]:
    """
    Execute a single wave of steps in parallel using asyncio.gather().

    Data Registry LOT 5.2: Accumulates registry items from registry-enabled tools.
    Data Registry LOT 4.3: Collects draft_info from tools requiring confirmation.

    Args:
        next_wave: Set of step IDs to execute in this wave
        steps_by_id: Lookup dict of all steps {step_id: ExecutionStep}
        completed_steps: Steps completed so far (for reference resolution)
        execution_plan: The execution plan being executed
        config: RunnableConfig with user_id, thread_id
        store: AsyncPostgresStore for tool context management
        context: Conversation context data (for context.X resolution)
        current_wave_id: Current wave number (for metrics)
        run_id: Run ID for logging
        accumulated_registry: Optional dict to accumulate data registry items (modified in-place)
        accumulated_drafts: Optional list to accumulate draft_info (modified in-place)
        current_turn_touched_ids: Optional set to track IDs added/updated this turn (modified in-place)

    Returns:
        List of StepResult objects (one per step in wave)

    Algorithm:
        1. Log wave start
        2. Build asyncio tasks for all steps in wave
        3. Execute tasks in parallel with asyncio.gather()
        4. Merge results into completed_steps
        5. Accumulate data registry items
        6. Collect draft_info for HITL flow
        7. Auto-save tool contexts after wave completion
        8. Log wave completion

    Best Practices (2025):
        - True parallel execution (native asyncio)
        - Comprehensive logging for debugging
        - Auto-save contexts after wave (consistency)
        - Data registry accumulation for SSE side-channel
        - Draft collection for HITL draft_critique flow
    """
    wave_start_time = time.time()

    logger.info(
        "wave_execution_started",
        run_id=run_id,
        plan_id=execution_plan.plan_id,
        wave_id=current_wave_id,
        wave_size=len(next_wave),
        step_ids=sorted(next_wave),
    )

    # Build tasks for asyncio.gather()
    # INTELLIA LocalQueryEngine: Pass accumulated_registry for local_query_engine_tool injection
    # BugFix 2025-12-19: Pass turn_id for RegistryItem.meta injection
    # FIX 2026-02-06: Convert set to sorted list ONCE for consistent ordering
    # This ensures exception handling can correctly map results back to steps
    step_ids_ordered = sorted(next_wave)
    tasks = [
        _execute_single_step_async(
            step=steps_by_id[step_id],
            completed_steps=completed_steps,
            config=config,
            wave_id=current_wave_id,
            store=store,
            context=context,
            accumulated_registry=accumulated_registry,
            turn_id=turn_id,
        )
        for step_id in step_ids_ordered
    ]

    # Execute in parallel with exception isolation
    # FIX 2026-02-06: Use return_exceptions=True to isolate step failures
    # Without this, one failing step cancels all parallel steps, causing
    # incomplete plan execution and data inconsistency
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert exceptions to failed StepResults for consistent handling
    step_results: list[StepResult] = []
    for i, result in enumerate(raw_results):
        if isinstance(result, Exception):
            step_id = step_ids_ordered[i]
            step = steps_by_id[step_id]
            logger.error(
                "step_execution_exception",
                step_id=step_id,
                tool_name=step.tool_name,
                error_type=type(result).__name__,
                error_message=str(result),
            )
            step_results.append(
                StepResult(
                    step_id=step_id,
                    step_type=step.step_type,
                    tool_name=step.tool_name,
                    success=False,
                    error=f"{type(result).__name__}: {result}",
                    error_code=ToolErrorCode.INTERNAL_ERROR,
                    execution_time_ms=0,
                    wave_id=current_wave_id,
                )
            )
        else:
            step_results.append(result)

    # Merge results into completed_steps
    # Data Registry LOT 5.2: Also accumulate registry items
    # Data Registry LOT 4.3: Also collect draft_info for HITL flow
    # BugFix 2025-12-01 v2: Track touched IDs for current turn filtering
    for step_result in step_results:
        _merge_single_step_result(
            completed_steps,
            step_result,
            accumulated_registry,
            accumulated_drafts,
            current_turn_touched_ids,
        )

    wave_execution_time_ms = int((time.time() - wave_start_time) * 1000)

    logger.info(
        "wave_execution_completed",
        run_id=run_id,
        plan_id=execution_plan.plan_id,
        wave_id=current_wave_id,
        steps_completed=len(step_results),
        execution_time_ms=wave_execution_time_ms,
        total_completed=len(completed_steps),
    )

    # Auto-save tool contexts after wave completion
    await _auto_save_wave_contexts(
        step_results=step_results,
        execution_plan=execution_plan,
        config=config,
        store=store,
        wave_id=current_wave_id,
    )

    return step_results


# ============================================================================
# Context Auto-Save (Post-Wave)
# ============================================================================


async def _auto_save_wave_contexts(
    step_results: list[StepResult],
    execution_plan: ExecutionPlan,
    config: RunnableConfig,
    store: Any,
    wave_id: int,
) -> None:
    """
    Auto-save tool contexts after a wave execution completes.

    This function is called after each wave completes to persist tool results
    to the context store (list/details/current). It consolidates results from
    all steps in the wave that produced context-worthy data.

    Why after wave (not after step):
    - Parallel execution: Multiple steps may run simultaneously
    - Consistency: Wait for full wave to avoid partial context states
    - Performance: Batch context saves reduce store operations

    Algorithm:
        1. Filter step_results to successful TOOL steps only
        2. For each step, lookup manifest from catalogue
        3. If manifest.context_key exists → call manager.auto_save()
        4. Handle errors gracefully (context save failures don't crash execution)

    Args:
        step_results: List of StepResult from the completed wave
        execution_plan: ExecutionPlan being executed (for step lookup)
        config: RunnableConfig with user_id, thread_id
        store: BaseStore for context persistence
        wave_id: Current wave ID (for logging)

    Example:
        >>> # After wave 0 completes with 2 steps:
        >>> # - Step "search" (get_contacts_tool) → 2 contacts found
        >>> # - Step "validate" (CONDITIONAL) → success
        >>> await _auto_save_wave_contexts(
        ...     step_results=[search_result, validate_result],
        ...     execution_plan=plan,
        ...     config=config,
        ...     store=store,
        ...     wave_id=0,
        ... )
        >>> # Result: Saves contacts to Store (list + auto-set current if 1 item)

    Context Save Logic (from manager.auto_save):
        - LIST mode: Overwrites list (search/list tools) + auto-manage current
        - CURRENT mode: Set current only (direct ID fetch), never touches list
        - Decorated tools signal _tcm_saved=True → skipped here (no double-save)

    Error Handling:
        - Auto-save failures are logged but DO NOT crash wave execution
        - Missing manifests → skip step (context tools don't have manifests)
        - Invalid tool results → skip step with warning

    Best Practices (2025):
        - Call after wave_execution_completed log
        - Use same config/store as step execution
        - Let manager.auto_save() handle classification (LIST vs DETAILS)
    """
    from src.domains.agents.context.manager import ToolContextManager
    from src.domains.agents.registry import get_global_registry
    from src.domains.agents.registry.catalogue import ToolManifestNotFound

    # Get global registry for manifest lookup
    registry = get_global_registry()
    manager = ToolContextManager()

    # Extract user_id and session_id from config
    user_id = config.get("configurable", {}).get(FIELD_USER_ID)
    session_id = config.get("configurable", {}).get("thread_id", "")

    # Check store is available
    if not store:
        logger.warning(
            "auto_save_wave_skipped_missing_store",
            wave_id=wave_id,
        )
        return

    if not user_id:
        logger.warning(
            "auto_save_wave_skipped_missing_user_id",
            wave_id=wave_id,
        )
        return

    # Counter for logging
    saved_count = 0
    skipped_count = 0

    # Iterate over step results
    for step_result in step_results:
        # Only process successful TOOL steps
        if not step_result.success or step_result.step_type != StepType.TOOL:
            continue

        # Lookup step from execution plan
        step = next(
            (s for s in execution_plan.steps if s.step_id == step_result.step_id),
            None,
        )
        if not step:
            logger.warning(
                "auto_save_step_not_found_in_plan",
                step_id=step_result.step_id,
                wave_id=wave_id,
            )
            skipped_count += 1
            continue

        # Lookup manifest from catalogue
        # NOTE: get_tool_manifest() takes only tool_name (not agent_name)
        # Tools are globally unique in the catalogue
        try:
            manifest = registry.get_tool_manifest(step.tool_name)
        except (KeyError, ValueError, AttributeError, ToolManifestNotFound) as e:
            # Context tools (resolve_reference, etc.) don't have manifests.
            # User MCP tools (evolution F2) have manifests in ContextVar,
            # not in the global registry → ToolManifestNotFound.
            # Both cases: skip auto-save (no context_key for these tools).
            logger.debug(
                "auto_save_manifest_not_found",
                step_id=step_result.step_id,
                agent=step.agent_name,
                tool=step.tool_name,
                error=str(e),
            )
            skipped_count += 1
            continue

        # Check if tool has context_key (context-producing tools)
        if not manifest.context_key:
            # Tool doesn't produce context (e.g., CONDITIONAL, utility tools)
            skipped_count += 1
            continue

        # Extract result data for auto-save
        # step_result.result is the raw tool output (dict)
        result_data = step_result.result

        if not isinstance(result_data, dict):
            logger.warning(
                "auto_save_invalid_result_type",
                step_id=step_result.step_id,
                result_type=type(result_data).__name__,
                wave_id=wave_id,
            )
            skipped_count += 1
            continue

        # Skip if decorator already saved this tool's context (prevents double-save).
        # @auto_save_context sets _tcm_saved=True on tool_metadata after save.
        if result_data.get("_tcm_saved"):
            skipped_count += 1
            logger.debug(
                "auto_save_wave_skipped_already_saved",
                step_id=step_result.step_id,
                tool=step.tool_name,
            )
            continue

        # Inject tool_name for manager's classification
        enriched_result_data = {
            **result_data,
            FIELD_TOOL_NAME: step.tool_name,
        }

        # Build RunnableConfig for auto_save (same pattern as plan_executor.py)
        config_dict = {
            "configurable": {
                FIELD_USER_ID: str(user_id),
                "thread_id": session_id,
            },
            FIELD_METADATA: {FIELD_TURN_ID: wave_id},
        }
        save_config = RunnableConfig(**config_dict)

        try:
            # Save mode resolution for tools without decorator (e.g. MCP):
            # 1. tool output context_save_mode (rare, but possible)
            # 2. manifest.context_save_mode (legacy manifest opt-in)
            # 3. None → classify_save_mode defaults to LIST
            dynamic_mode = result_data.get("context_save_mode")
            effective_mode = (
                dynamic_mode if dynamic_mode is not None else manifest.context_save_mode
            )

            await manager.auto_save(
                context_type=manifest.context_key,
                result_data=enriched_result_data,
                config=save_config,
                store=store,
                explicit_mode=effective_mode,
            )

            saved_count += 1

            logger.info(
                "context_auto_saved_wave",
                step_id=step_result.step_id,
                context_key=manifest.context_key,
                wave_id=wave_id,
                user_id=str(user_id),
                session_id=session_id,
            )

        except (ValueError, KeyError, RuntimeError, AttributeError, OSError) as e:
            # Auto-save failures are non-fatal (defensive programming)
            logger.error(
                "context_auto_save_failed_wave",
                step_id=step_result.step_id,
                context_key=manifest.context_key,
                wave_id=wave_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            skipped_count += 1

    # Summary log
    if saved_count > 0 or skipped_count > 0:
        logger.info(
            "wave_context_auto_save_summary",
            wave_id=wave_id,
            saved_count=saved_count,
            skipped_count=skipped_count,
            total_steps=len(step_results),
        )


# ============================================================================
# Main Parallel Executor
# ============================================================================


async def execute_plan_parallel(
    execution_plan: ExecutionPlan,
    config: RunnableConfig,
    run_id: str,
    initial_registry: dict[str, Any] | None = None,
    turn_id: int | None = None,
    initial_completed_steps: dict[str, dict[str, Any]] | None = None,
    pre_executed_registry: dict[str, Any] | None = None,
) -> ParallelExecutionResult:
    """
    Execute ExecutionPlan with true parallel execution using asyncio.

    Phase 5.2B-asyncio: Replaces broken LangGraph Command+Send pattern.
    Data Registry LOT 5.2: Accumulates registry items from registry-enabled tools.
    BugFix 2025-11-30: Added initial_registry to support items[N].field resolution
                       from previous turns (e.g., "details du premier" after search).
    BugFix 2025-12-19: Added turn_id to inject into RegistryItem.meta for context resolution.
    BugFix 2026-01-19: Added initial_completed_steps for FOR_EACH HITL pre-execution.
                       When provider steps are pre-executed for accurate HITL count,
                       their results are passed here to avoid re-execution.
    BugFix 2026-01-24: Added pre_executed_registry to preserve registry items from pre-executed
                       steps. Unlike initial_registry (from previous turns), these items ARE
                       included in current_turn_touched_ids so they appear in the final registry.

    Args:
        execution_plan: ExecutionPlan to execute
        config: RunnableConfig with user_id, thread_id
        run_id: Run ID for logging/tracing
        initial_registry: Registry from state with items from previous turns
                          (required for items[N].field reference resolution)
        turn_id: Current turn ID to inject into RegistryItem.meta (for context resolution filtering)
        initial_completed_steps: Pre-executed step results (for FOR_EACH HITL flow).
                                 Steps in this dict will be skipped during execution.
        pre_executed_registry: Registry items from pre-executed steps (FOR_EACH HITL flow).
                              These are added to BOTH accumulated_registry AND current_turn_touched_ids.

    Returns:
        ParallelExecutionResult with:
        - completed_steps: Dict mapping step_id -> result data
        - registry: Dict of data registry items (accumulated from all tools)

    Algorithm:
        1. Build dependency graph
        2. Calculate waves (topological sort)
        3. For each wave:
            a. Execute all steps in parallel using asyncio.gather()
            b. Merge results into completed_steps
            c. Accumulate data registry items
            d. Handle CONDITIONAL branching (identify skipped steps)
        4. Return ParallelExecutionResult

    Example:
        >>> plan = ExecutionPlan(steps=[
        ...     Step(id="search", tool="search_tool"),
        ...     Step(id="validate", tool="validate_tool", depends_on=["search"]),
        ... ])
        >>> result = await execute_plan_parallel(plan, config, "run123")
        >>> print(result.completed_steps)
        {"search": {...}, "validate": {...}}
        >>> print(result.registry)
        {"contact_abc": {...}, "contact_def": {...}}
    """
    # LangGraph v1.0: Store is NOT accessible via config in standalone functions
    # Store is ONLY injected in tools via InjectedStore pattern
    # For standalone functions called from nodes, we must use the global Store singleton
    from src.domains.agents.context.store import get_tool_context_store

    store = await get_tool_context_store()

    # Phase 8.5: Load ALL active contexts from store for context.X reference resolution
    # Session 22 - Helper #1: Context loading extracted for clarity
    context = await _load_execution_contexts(config, store, run_id)

    logger.info(
        "parallel_execution_started",
        run_id=run_id,
        plan_id=execution_plan.plan_id,
        total_steps=len(execution_plan.steps),
        has_store=store is not None,
        has_context=len(context) > 0,
    )

    # LOT 6 FIX: Handle empty plans gracefully
    # When max_iterations is reached in planner, the plan may have 0 steps
    # Return valid empty result instead of crashing on max() with empty iterable
    if not execution_plan.steps:
        logger.warning(
            "parallel_execution_empty_plan",
            run_id=run_id,
            plan_id=execution_plan.plan_id,
            msg="Plan has no steps to execute - returning empty result",
        )
        return ParallelExecutionResult(
            completed_steps={},
            registry={},
        )

    start_time = time.time()

    # Build dependency graph and calculate waves
    dep_graph = DependencyGraph(execution_plan)

    # Get initial wave info for metrics
    wave_info = dep_graph.get_wave_info()
    logger.info(
        "dependency_graph_analyzed",
        run_id=run_id,
        plan_id=execution_plan.plan_id,
        wave_info=wave_info,
    )

    # Execute waves iteratively
    # BugFix 2026-01-19: Initialize with pre-executed steps (FOR_EACH HITL flow)
    # When provider steps are pre-executed for accurate HITL count, they're passed here
    # to avoid re-execution. The dependency graph will skip these steps.
    completed_steps: dict[str, dict[str, Any]] = (
        dict(initial_completed_steps) if initial_completed_steps else {}
    )
    steps_by_id = {step.step_id: step for step in execution_plan.steps}
    current_wave_id = 0

    if initial_completed_steps:
        logger.info(
            "parallel_execution_using_pre_executed_steps",
            run_id=run_id,
            plan_id=execution_plan.plan_id,
            pre_executed_step_ids=list(initial_completed_steps.keys()),
        )

    # Data Registry LOT 5.2: Accumulate registry items from all registry-enabled tools
    # BugFix 2025-12-01: Separate initial_registry from current_turn_registry
    # - initial_registry: Items from previous turns (for items[N].field resolution)
    # - current_turn_registry: Items MODIFIED/ADDED this turn (for response_node filtering)
    # Previous bug: Mixing both caused response_node to show old items instead of new search results
    #
    # BugFix 2025-12-01 v2: Track MODIFIED items, not just new IDs
    # When get_contact_details updates an existing contact with enriched data,
    # the item must be included even if the ID already existed.
    # Solution: Track IDs that were touched this turn (added or updated)

    # For reference resolution: combine initial + current turn items
    accumulated_registry: dict[str, Any] = dict(initial_registry) if initial_registry else {}

    # Track IDs that are TOUCHED this turn (added or updated by tools)
    # This replaces the previous approach of excluding initial_registry_ids
    current_turn_touched_ids: set[str] = set()

    # BugFix 2026-01-24: Add pre-executed registry items to BOTH accumulated and touched
    # This preserves parent items (e.g., events from get_events_tool) when child steps
    # (e.g., routes) fail due to invalid destinations
    if pre_executed_registry:
        accumulated_registry.update(pre_executed_registry)
        current_turn_touched_ids.update(pre_executed_registry.keys())
        logger.info(
            "pre_executed_registry_propagated",
            run_id=run_id,
            pre_executed_count=len(pre_executed_registry),
            total_accumulated=len(accumulated_registry),
        )

    # Data Registry LOT 4.3: Collect draft_info from tools requiring confirmation
    accumulated_drafts: list[dict[str, Any]] = []

    # Track steps to exclude (CONDITIONAL branches not taken)
    # Updated after each wave containing CONDITIONAL steps
    excluded_steps: set[str] = set()

    while True:
        # =====================================================================
        # FOR_EACH PRE-EXPANSION CHECK (DRY - uses shared helper)
        # =====================================================================
        # BugFix 2026-01-19: Check FOR_EACH expansion BEFORE calculating next wave.
        # This is critical when initial_completed_steps contains pre-executed providers.
        # Without this check:
        # - get_next_wave() returns the unexpanded FOR_EACH step
        # - $item references are NOT substituted (step not expanded)
        # - Tool execution fails with literal "$item.field" values
        # =====================================================================
        expansion_result = await _expand_and_execute_for_each_if_ready(
            execution_plan=execution_plan,
            dep_graph=dep_graph,
            steps_by_id=steps_by_id,
            completed_steps=completed_steps,
            excluded_steps=excluded_steps,
            config=config,
            store=store,
            context=context,
            current_wave_id=current_wave_id,
            run_id=run_id,
            accumulated_registry=accumulated_registry,
            accumulated_drafts=accumulated_drafts,
            current_turn_touched_ids=current_turn_touched_ids,
            turn_id=turn_id,
        )
        if expansion_result:
            execution_plan, dep_graph, steps_by_id = expansion_result

        # Calculate next wave based on completed steps AND excluded steps
        # This is dynamic to handle CONDITIONAL branching
        # CRITICAL: excluded_steps prevents skipped branches from executing
        _unfiltered_wave = dep_graph.get_next_wave(
            completed=set(completed_steps.keys()), excluded=set()
        )
        next_wave = dep_graph.get_next_wave(
            completed=set(completed_steps.keys()), excluded=excluded_steps
        )

        # Dashboard 15: wave filtered counter (skipped-branch exclusion)
        try:
            from src.infrastructure.observability.metrics_agents import (
                langgraph_plan_wave_filtered_total,
            )

            filtered_count = len(_unfiltered_wave) - len(next_wave)
            if filtered_count > 0:
                _plan_type = getattr(execution_plan, "execution_mode", "pipeline") or "pipeline"
                langgraph_plan_wave_filtered_total.labels(
                    plan_type=_plan_type, filter_type="excluded_steps"
                ).inc(filtered_count)
        except Exception:
            pass

        if not next_wave:
            # No more steps can execute - check if plan complete or deadlocked
            # Session 22 - Helper #2: Plan completion check extracted
            is_complete, is_deadlocked = _check_plan_completion(
                execution_plan, completed_steps, run_id
            )
            break  # Exit loop regardless of completion status

        # Execute wave in parallel (Session 22 - Helper #3)
        # Data Registry LOT 5.2: Pass accumulated_registry for registry item collection
        # Data Registry LOT 4.3: Pass accumulated_drafts for draft_info collection
        # BugFix 2025-12-19: Pass turn_id for RegistryItem.meta injection
        await _execute_wave_parallel(
            next_wave=next_wave,
            steps_by_id=steps_by_id,
            completed_steps=completed_steps,
            execution_plan=execution_plan,
            config=config,
            store=store,
            context=context,
            current_wave_id=current_wave_id,
            run_id=run_id,
            accumulated_registry=accumulated_registry,
            accumulated_drafts=accumulated_drafts,
            current_turn_touched_ids=current_turn_touched_ids,
            turn_id=turn_id,
        )

        # =====================================================================
        # FOR_EACH EXPANSION: Expand for_each steps when provider completes
        # =====================================================================
        # After wave completes, check if any pending for_each steps can be expanded.
        # Uses shared helper to avoid code duplication (DRY).
        # =====================================================================
        expansion_result = await _expand_and_execute_for_each_if_ready(
            execution_plan=execution_plan,
            dep_graph=dep_graph,
            steps_by_id=steps_by_id,
            completed_steps=completed_steps,
            excluded_steps=excluded_steps,
            config=config,
            store=store,
            context=context,
            current_wave_id=current_wave_id,
            run_id=run_id,
            accumulated_registry=accumulated_registry,
            accumulated_drafts=accumulated_drafts,
            current_turn_touched_ids=current_turn_touched_ids,
            turn_id=turn_id,
        )
        if expansion_result:
            execution_plan, dep_graph, steps_by_id = expansion_result

        # CRITICAL FIX: After wave execution, identify newly skipped steps
        # If this wave contained CONDITIONAL steps, their untaken branches
        # must be excluded from future waves
        newly_skipped = _identify_skipped_steps(execution_plan, completed_steps)
        if newly_skipped - excluded_steps:
            # New steps to skip (CONDITIONAL branch not taken)
            added_skips = newly_skipped - excluded_steps
            excluded_steps.update(added_skips)
            logger.info(
                "conditional_branches_excluded",
                run_id=run_id,
                plan_id=execution_plan.plan_id,
                wave_id=current_wave_id,
                newly_excluded=sorted(added_skips),
                total_excluded=sorted(excluded_steps),
            )

        current_wave_id += 1

    total_execution_time_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "parallel_execution_completed",
        run_id=run_id,
        plan_id=execution_plan.plan_id,
        total_steps=len(execution_plan.steps),
        completed_steps=len(completed_steps),
        total_waves=current_wave_id,
        total_time_ms=total_execution_time_ms,
    )

    # DEBUG: Log completed_steps structure to diagnose reference resolution issues
    logger.info(
        "parallel_execution_completed_steps_structure",
        run_id=run_id,
        plan_id=execution_plan.plan_id,
        completed_steps_keys=list(completed_steps.keys()),
        search_step_structure=(
            completed_steps.get("search") if "search" in completed_steps else "NOT_FOUND"
        ),
    )

    # BugFix 2025-12-01 v2: Return items TOUCHED this turn (new + updated)
    # This allows response_node to correctly show updated details, not just new items
    # Previous approach excluded updates to existing items (e.g., get_contact_details on search result)
    #
    # BugFix 2025-12-07: PRESERVE INSERTION ORDER from accumulated_registry
    # Previous bug: Iterating over current_turn_touched_ids (a set) loses order
    # because sets don't preserve insertion order. This caused resolve_reference
    # to return wrong items (e.g., "3rd email" returned 1st email).
    # Fix: Iterate over accumulated_registry (dict preserves order) and filter by IDs.
    current_turn_registry = {
        item_id: item
        for item_id, item in accumulated_registry.items()
        if item_id in current_turn_touched_ids
    }

    # Data Registry LOT 5.2: Log accumulated registry if non-empty
    if current_turn_registry:
        initial_registry_count = len(initial_registry) if initial_registry else 0
        logger.info(
            "registry_execution_complete",
            run_id=run_id,
            plan_id=execution_plan.plan_id,
            current_turn_items=len(current_turn_registry),
            inherited_items=initial_registry_count,
            total_items=len(accumulated_registry),
            current_turn_ids=list(current_turn_registry.keys()),
        )

    # Data Registry LOT 4.3: Build pending drafts from accumulated draft info
    pending_draft: PendingDraftInfo | None = None
    pending_drafts: list[PendingDraftInfo] = []

    if accumulated_drafts:
        for draft_dict in accumulated_drafts:
            draft_info = PendingDraftInfo(
                draft_id=draft_dict.get("draft_id", ""),
                draft_type=draft_dict.get("draft_type", ""),
                draft_content=draft_dict.get("draft_content", {}),
                draft_summary=draft_dict.get("draft_summary", ""),
                registry_ids=draft_dict.get("registry_ids", []),
                tool_name=draft_dict.get("tool_name"),
                step_id=draft_dict.get("step_id"),
            )
            pending_drafts.append(draft_info)

        # Backwards compat: pending_draft = first draft (single-draft path)
        pending_draft = pending_drafts[0]

        logger.info(
            "registry_draft_execution_complete",
            run_id=run_id,
            plan_id=execution_plan.plan_id,
            draft_id=pending_draft.draft_id,
            draft_type=pending_draft.draft_type,
            total_drafts_count=len(pending_drafts),
        )

    # Return only current turn's new items in registry
    # (accumulated_registry includes initial_registry for reference resolution,
    #  but we only return current_turn_registry to response_node)
    return ParallelExecutionResult(
        completed_steps=completed_steps,
        registry=current_turn_registry,
        pending_draft=pending_draft,
        pending_drafts=pending_drafts,
    )


# ============================================================================
# Single Step Execution
# ============================================================================


async def _execute_single_step_async(
    step: ExecutionStep,
    completed_steps: dict[str, dict[str, Any]],
    config: RunnableConfig,
    wave_id: int,
    store: Any,
    context: dict[str, Any] | None = None,
    accumulated_registry: dict[str, Any] | None = None,
    turn_id: int | None = None,
) -> StepResult:
    """
    Execute a single step (TOOL or CONDITIONAL) asynchronously.

    Copied/adapted from step_executor_node.step_executor_node().
    BugFix 2025-12-19: Added turn_id for RegistryItem.meta injection.

    Args:
        step: ExecutionStep to execute
        completed_steps: Map of step_id -> result data (for reference resolution)
        config: RunnableConfig with user_id, thread_id
        wave_id: Current wave number (for metrics)
        store: AsyncPostgresStore for tool context management
        context: Conversation context data (optional, for context.X reference resolution)
        accumulated_registry: INTELLIA LocalQueryEngine - registry items for local_query_engine_tool
        turn_id: Current turn ID to inject into RegistryItem.meta (for context resolution)

    Returns:
        StepResult with execution result
    """
    # Enrich config with step_id for token tracking
    enriched_config = config.copy()
    if FIELD_METADATA not in enriched_config:
        enriched_config[FIELD_METADATA] = {}
    enriched_config[FIELD_METADATA][FIELD_NODE_NAME] = f"parallel_executor:{step.step_id}"

    # Get timeout from step or use default, capped at MAX
    # F6: Sub-agent delegation needs more time (full graph execution)
    # Image generation needs more time (OpenAI API can take 30-60s for high quality)
    _SUBAGENT_TOOL_TIMEOUT = 120.0
    _IMAGE_TOOL_TIMEOUT = 90.0
    _DEVOPS_TOOL_TIMEOUT = 120.0  # Claude CLI can take 15-60s per investigation
    _IMAGE_TOOLS = {"generate_image", "edit_image"}
    _HIGH_LATENCY_TOOLS = _IMAGE_TOOLS | {"delegate_to_sub_agent_tool", "claude_server_task_tool"}
    if step.tool_name == "delegate_to_sub_agent_tool":
        effective_default = _SUBAGENT_TOOL_TIMEOUT
    elif step.tool_name in _IMAGE_TOOLS:
        effective_default = _IMAGE_TOOL_TIMEOUT
    elif step.tool_name == "claude_server_task_tool":
        effective_default = _DEVOPS_TOOL_TIMEOUT
    else:
        effective_default = DEFAULT_TOOL_TIMEOUT_SECONDS
    # Use max(step, default) for tools with known high latency (image gen, sub-agents, devops)
    # to prevent the planner from imposing a too-short timeout
    if step.tool_name in _HIGH_LATENCY_TOOLS:
        timeout_seconds = min(
            max(step.timeout_seconds or effective_default, effective_default),
            MAX_TOOL_TIMEOUT_SECONDS,
        )
    else:
        timeout_seconds = min(
            step.timeout_seconds or effective_default,
            MAX_TOOL_TIMEOUT_SECONDS,
        )

    logger.info(
        "step_execution_started",
        step_id=step.step_id,
        step_type=step.step_type.value,
        wave_id=wave_id,
        dependencies_count=len(step.depends_on or []),
        timeout_seconds=timeout_seconds,
    )

    start_time = time.time()

    try:
        # Lazy import for catch-all (avoids circular imports)
        from src.domains.agents.registry.catalogue import CatalogueError

        # Route to step type handler with timeout
        if step.step_type == StepType.TOOL:
            result = await asyncio.wait_for(
                _execute_tool_step(
                    step=step,
                    completed_steps=completed_steps,
                    config=enriched_config,
                    wave_id=wave_id,
                    store=store,
                    accumulated_registry=accumulated_registry,
                    context=context,  # Phase 8.5: Pass context for context.X reference resolution
                    turn_id=turn_id,  # BugFix 2025-12-19: For RegistryItem.meta injection
                ),
                timeout=timeout_seconds,
            )
        elif step.step_type == StepType.CONDITIONAL:
            # CONDITIONAL steps are fast - use short timeout
            result = await asyncio.wait_for(
                _execute_conditional_step(
                    step=step,
                    completed_steps=completed_steps,
                    wave_id=wave_id,
                ),
                timeout=HTTP_TIMEOUT_CONDITIONAL_EVAL,
            )
        else:
            # Unsupported step type
            execution_time_ms = int((time.time() - start_time) * 1000)
            result = StepResult(
                step_id=step.step_id,
                step_type=step.step_type,
                success=False,
                error=f"Unsupported step type: {step.step_type.value}",
                error_code=ToolErrorCode.INVALID_INPUT,
                execution_time_ms=execution_time_ms,
                wave_id=wave_id,
            )

        logger.info(
            "step_execution_completed",
            step_id=step.step_id,
            success=result.success,
            execution_time_ms=result.execution_time_ms,
            wave_id=wave_id,
        )

        return result

    except TimeoutError:
        # Step timed out
        execution_time_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "step_execution_timeout",
            step_id=step.step_id,
            step_type=step.step_type.value,
            timeout_seconds=timeout_seconds,
            execution_time_ms=execution_time_ms,
            wave_id=wave_id,
        )

        return StepResult(
            step_id=step.step_id,
            step_type=step.step_type,
            tool_name=step.tool_name if step.step_type == StepType.TOOL else None,
            args=step.parameters if step.step_type == StepType.TOOL else None,
            success=False,
            error=f"Step timed out after {timeout_seconds} seconds",
            error_code=ToolErrorCode.TIMEOUT,
            execution_time_ms=execution_time_ms,
            wave_id=wave_id,
        )

    except (
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        OSError,
        CatalogueError,
    ) as e:
        # Catch-all: Step execution failed with unexpected error
        execution_time_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "step_execution_unexpected_error",
            step_id=step.step_id,
            step_type=step.step_type.value,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )

        return StepResult(
            step_id=step.step_id,
            step_type=step.step_type,
            success=False,
            error=f"Unexpected error: {e!s}",
            error_code=ToolErrorCode.INTERNAL_ERROR,
            execution_time_ms=execution_time_ms,
            wave_id=wave_id,
        )


# ============================================================================
# Tool Runtime Injection (Session 22)
# ============================================================================


def _build_tool_runtime(
    tool: Any,
    args: dict[str, Any],
    config: RunnableConfig,
    store: Any,
) -> dict[str, Any]:
    """
    Build ToolRuntime and inject into args if tool requires it.

    Args:
        tool: LangChain tool instance
        args: Tool arguments
        config: RunnableConfig with user_id, thread_id
        store: AsyncPostgresStore for context management

    Returns:
        Updated args dict with ToolRuntime injected (if needed)

    Algorithm:
        1. Check tool schema for "runtime" parameter
        2. If found, build ToolRuntime with store injection
        3. Inject runtime into args dict
        4. Return updated args

    Best Practices (2025):
        - LangGraph v1.0 pattern: Store passed explicitly (not from config)
        - NullStreamWriter for non-graph execution
        - Clear separation of runtime injection logic
    """
    from langchain.tools import ToolRuntime
    from langchain_core.tools.base import get_all_basemodel_annotations

    # Check if tool needs ToolRuntime injection
    full_schema = tool.get_input_schema()
    runtime_arg_name = None

    for name, _type in get_all_basemodel_annotations(full_schema).items():
        if name == "runtime":
            runtime_arg_name = name
            break

    # Inject ToolRuntime if needed
    if runtime_arg_name:
        # DEBUG: Log config.configurable keys to diagnose __user_message propagation
        configurable = config.get("configurable", {}) if config else {}
        logger.debug(
            "injecting_tool_runtime",
            tool=tool.name,
            runtime_arg=runtime_arg_name,
            configurable_keys=list(configurable.keys()),
            has_user_message="__user_message" in configurable,
        )

        # Construct ToolRuntime (minimal, no state/context)
        # LangGraph v1.0: Store is NOT accessible via config in standalone functions
        # Store is passed explicitly from execute_plan_parallel() via get_tool_context_store()
        runtime = ToolRuntime(
            state=None,  # Not available in worker context
            config=config,
            context=None,  # Not available in worker context
            store=store,  # Passed explicitly from execute_plan_parallel()
            stream_writer=NullStreamWriter(),  # Session 22: Use module-level NullStreamWriter
            tool_call_id=None,  # No tool call ID outside graph
        )

        # Inject into args
        return {**args, runtime_arg_name: runtime}

    return args


# ============================================================================
# Tool Result Parsing (Session 22)
# ============================================================================


def _parse_tool_result(result: Any) -> dict[str, Any]:
    """
    Parse tool result from ToolMessage to standardized dict format.

    Args:
        result: Tool result (ToolMessage, dict, str, or other)

    Returns:
        Standardized dict with success, data, error fields

    Algorithm:
        1. Extract content from ToolMessage (if ToolMessage)
        2. If dict: return as-is
        3. If str: try to parse as JSON
        4. If JSON parse succeeds and is dict: return dict
        5. If JSON parse fails: wrap in success dict with result field
        6. Unknown format: wrap in success dict

    Best Practices (2025):
        - Handle all LangChain tool return formats
        - Parse JSON strings (many tools return ToolResponse.model_dump_json())
        - Graceful fallback for unknown formats
        - Clear separation of parsing logic
    """
    from langchain_core.messages import ToolMessage

    # Extract content from ToolMessage if needed
    if isinstance(result, ToolMessage):
        content = result.content
    else:
        # Fallback for legacy tools that return raw values
        content = result

    # Parse content (can be str or dict)
    if isinstance(content, dict):
        return content
    elif isinstance(content, str):
        # Tool returned string - try to parse as JSON first
        # Many tools in this codebase return ToolResponse.model_dump_json()
        # which needs to be parsed before use
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                # Successfully parsed JSON object - return as-is
                return parsed
            else:
                # Parsed but not a dict (rare) - wrap it
                return {
                    "success": True,
                    "data": {FIELD_RESULT: parsed},
                    "message": content,
                }
        except (json.JSONDecodeError, ValueError):
            # Not JSON - treat as plain string (legacy format)
            return {
                "success": True,
                "data": {FIELD_RESULT: content},
                "message": content,
            }
    else:
        # Unknown format
        return {
            "success": True,
            "data": {FIELD_RESULT: content},
        }


# ============================================================================
# Tool Step Execution
# ============================================================================


# ============================================================================
# Step Reference Resolution (Session 22 - Helper #6)
# ============================================================================


def _resolve_step_references(
    step: ExecutionStep,
    completed_steps: dict[str, dict[str, Any]],
    context: dict[str, Any] | None,
    start_time: float,
    wave_id: int,
    registry: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, StepResult | None]:
    """
    Resolve references in step parameters ($steps.X, context.X, and items[N].field).

    Session 22 - Helper #6: Extracted from _execute_tool_step() for clarity.
    BugFix 2025-11-30: Added registry parameter to support items[N].field resolution.

    Args:
        step: ExecutionStep with parameters to resolve
        completed_steps: Map of step_id -> result data
        context: Conversation context data (optional)
        start_time: Step execution start time
        wave_id: Current wave number
        registry: Data registry from state (optional, for items[N].field resolution)

    Returns:
        Tuple of (resolved_args, error_result):
        - If successful: (resolved_args, None)
        - If failed: (None, StepResult with error)

    Algorithm:
        1. Create ReferenceResolver
        2. Call resolve_args() with parameters, completed_steps, context, registry
        3. If ValueError/KeyError: return error StepResult
        4. If success: return resolved args
    """
    resolver = ReferenceResolver()

    try:
        resolved_args = resolver.resolve_args(
            step.parameters or {}, completed_steps, context, registry
        )
        return resolved_args, None
    except (ValueError, KeyError) as e:
        logger.error(
            "reference_resolution_failed",
            step_id=step.step_id,
            tool=step.tool_name,
            args=step.parameters,
            error=str(e),
            exc_info=True,
        )
        execution_time_ms = int((time.time() - start_time) * 1000)
        error_result = StepResult(
            step_id=step.step_id,
            step_type=StepType.TOOL,
            tool_name=step.tool_name,
            args=step.parameters,
            success=False,
            error=f"Failed to resolve references: {e!s}",
            error_code=ToolErrorCode.INVALID_INPUT,
            execution_time_ms=execution_time_ms,
            wave_id=wave_id,
        )
        return None, error_result


# ============================================================================
# Tool Manifest Lookup (Session 22 - Helper #7)
# ============================================================================


def _get_tool_manifest_for_step(
    step: ExecutionStep,
    resolved_args: dict[str, Any],
    start_time: float,
    wave_id: int,
) -> tuple[Any | None, StepResult | None]:
    """
    Get tool manifest from registry with error handling.

    Session 22 - Helper #7: Extracted from _execute_tool_step() for clarity.

    Args:
        step: ExecutionStep with tool_name
        resolved_args: Resolved step parameters
        start_time: Step execution start time
        wave_id: Current wave number

    Returns:
        Tuple of (manifest, error_result):
        - If successful: (ToolManifest, None)
        - If failed: (None, StepResult with error)

    Algorithm:
        1. Get global registry
        2. Call get_tool_manifest(tool_name)
        3. If Exception: return error StepResult
        4. If success: return manifest
    """
    try:
        from src.domains.agents.registry import get_global_registry
        from src.domains.agents.registry.catalogue import ToolManifestNotFound

        registry = get_global_registry()
        manifest = registry.get_tool_manifest(step.tool_name)
        return manifest, None
    except (
        KeyError,
        ValueError,
        AttributeError,
        RuntimeError,
        ToolManifestNotFound,
    ) as e:
        # Fallback: MCP tools with hallucinated suffix (evolution F2.1/F2.5)
        from src.core.context import (
            strip_hallucinated_mcp_suffix,
            user_mcp_tools_ctx,
        )

        manifest = None

        # 1. Admin MCP: strip suffix and retry central registry
        stripped = strip_hallucinated_mcp_suffix(step.tool_name)
        if stripped:
            try:
                manifest = registry.get_tool_manifest(stripped)
                step.tool_name = stripped
                return manifest, None
            except Exception:
                pass

        # 2. User MCP: ContextVar with fuzzy resolve
        user_ctx = user_mcp_tools_ctx.get()
        if user_ctx:
            manifest = user_ctx.resolve_tool_manifest(step.tool_name)
            if manifest:
                if manifest.name != step.tool_name:
                    logger.info(
                        "tool_name_corrected",
                        original=step.tool_name,
                        corrected=manifest.name,
                        step_id=step.step_id,
                    )
                    step.tool_name = manifest.name
                return manifest, None

        logger.error(
            "tool_manifest_not_found",
            step_id=step.step_id,
            tool=step.tool_name,
            error=str(e),
            error_type=type(e).__name__,
        )
        execution_time_ms = int((time.time() - start_time) * 1000)
        error_result = StepResult(
            step_id=step.step_id,
            step_type=StepType.TOOL,
            tool_name=step.tool_name,
            args=resolved_args,
            success=False,
            error=f"Tool manifest not found: {e!s}",
            error_code=ToolErrorCode.NOT_FOUND,
            execution_time_ms=execution_time_ms,
            wave_id=wave_id,
        )
        return None, error_result


# ============================================================================
# TOOL Step Execution
# ============================================================================


def _flatten_dict_values(d: dict) -> list:
    """
    Recursively extract all values from nested dict/list structure.
    Used for Jinja2 template detection in parameters.

    Issue #41: Helper function for template detection.

    Args:
        d: Dictionary potentially containing nested dicts/lists

    Returns:
        Flat list of all leaf values

    Example:
        >>> _flatten_dict_values({"a": "{{ x }}", "b": {"c": "{% if y %}"}})
        ["{{ x }}", "{% if y %}"]
    """
    values = []
    for v in d.values():
        if isinstance(v, dict):
            values.extend(_flatten_dict_values(v))
        elif isinstance(v, list):
            values.extend(v)
        else:
            values.append(v)
    return values


async def _execute_tool_step(
    step: ExecutionStep,
    completed_steps: dict[str, dict[str, Any]],
    config: RunnableConfig,
    wave_id: int,
    store: Any,
    accumulated_registry: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    turn_id: int | None = None,
) -> StepResult:
    """
    Execute a TOOL step.

    Copied from step_executor_node._execute_tool_step().
    Session 22: Refactored with 2 helpers (125 → ~88 lines, -30%).
    Issue #41: Added Jinja2 template evaluation (Phase 2.5) before $steps resolution.
    INTELLIA LocalQueryEngine: Pass accumulated_registry for local_query_engine_tool injection.
    BugFix 2025-12-19: Added turn_id for RegistryItem.meta injection.

    Execution Order:
        1. Jinja2 template evaluation (Issue #41)
        2. $steps.X reference resolution
        3. Tool execution

    Args:
        step: ExecutionStep with step_type=TOOL
        completed_steps: Map of step_id -> result data
        config: RunnableConfig (enriched with step_id)
        wave_id: Current wave number
        store: AsyncPostgresStore for tool context management
        accumulated_registry: INTELLIA LocalQueryEngine - registry items for local_query_engine_tool
        context: Conversation context data (optional, for context.X reference resolution)
        turn_id: Current turn ID to inject into RegistryItem.meta (for context resolution)

    Returns:
        StepResult with tool execution result
    """
    start_time = time.time()

    # Phase 2.5 - Issue #41: Evaluate Jinja2 templates in parameters
    # This MUST happen BEFORE $steps.X resolution (templates may contain conditions)
    # Order: Jinja2 evaluation (#41) → $steps resolution → API call
    #
    # MULTI-ORDINAL FIX (2026-01-02): Use _get_jinja_required_params for Jinja validation.
    # For one_of tools (batch mode), returns [] because Jinja evaluates one template at a time
    # and cannot validate OR logic. Real validation is done by _validate_required_params.
    required_params = _get_jinja_required_params(step.tool_name)

    # Check if parameters contain Jinja2 syntax
    has_jinja_templates = any(
        _jinja_evaluator.contains_jinja_syntax(str(v))
        for v in _flatten_dict_values(step.parameters or {})
    )

    if has_jinja_templates:
        logger.info(
            "jinja_templates_detected_in_step",
            step_id=step.step_id,
            tool_name=step.tool_name,
            param_count=len(step.parameters or {}),
            required_params=required_params,
        )

        try:
            # Evaluate all Jinja2 templates in parameters
            evaluated_params = _jinja_evaluator.evaluate_parameters(
                parameters=step.parameters or {},
                completed_steps=completed_steps,
                step_id=step.step_id,
                required_params=required_params,
            )

            # 2026-01: Compact embedded data structures in text parameters
            # When Jinja evaluates $steps.X.places, it produces full API payloads (~2000 tokens/item)
            # Text compaction detects these and compacts to ~60 tokens/item using payload_to_text()
            evaluated_params = compact_text_params(
                parameters=evaluated_params,
                tool_name=step.tool_name,
            )

            # Replace step parameters with evaluated values
            step.parameters = evaluated_params

            logger.info(
                "jinja_templates_evaluated_successfully",
                step_id=step.step_id,
                evaluated_param_count=len(evaluated_params),
            )

        except EmptyResultError as e:
            # Required parameter evaluated to empty string - fail-fast
            logger.error(
                "step_execution_failed_empty_jinja_result",
                step_id=step.step_id,
                tool_name=step.tool_name,
                error=str(e),
            )
            execution_time_ms = int((time.time() - start_time) * 1000)
            return StepResult(
                step_id=step.step_id,
                step_type=StepType.TOOL,
                tool_name=step.tool_name,
                args=step.parameters,
                success=False,
                error=f"Template evaluation failed: {e!s}",
                error_code=ToolErrorCode.TEMPLATE_EMPTY_RESULT,
                execution_time_ms=execution_time_ms,
                wave_id=wave_id,
            )

        except RecursionError as e:
            # Recursion depth limit exceeded - security protection
            logger.error(
                "step_execution_failed_recursion_limit",
                step_id=step.step_id,
                tool_name=step.tool_name,
                error=str(e),
            )
            execution_time_ms = int((time.time() - start_time) * 1000)
            return StepResult(
                step_id=step.step_id,
                step_type=StepType.TOOL,
                tool_name=step.tool_name,
                args=step.parameters,
                success=False,
                error=f"Template evaluation exceeded recursion limit: {e!s}",
                error_code=ToolErrorCode.TEMPLATE_RECURSION_LIMIT,
                execution_time_ms=execution_time_ms,
                wave_id=wave_id,
            )

        except (ValueError, KeyError, TypeError, RuntimeError, AttributeError) as e:
            # FAIL-FAST: Do NOT continue with original parameters (raw Jinja templates)
            # Passing unevaluated templates to tools causes confusing downstream errors
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "jinja_evaluation_critical_error",
                step_id=step.step_id,
                tool_name=step.tool_name,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return StepResult(
                step_id=step.step_id,
                step_type=StepType.TOOL,
                tool_name=step.tool_name,
                args=step.parameters,
                success=False,
                error=f"Jinja template evaluation failed: {type(e).__name__}: {e!s}",
                error_code=ToolErrorCode.TEMPLATE_EVALUATION_FAILED,
                execution_time_ms=execution_time_ms,
                wave_id=wave_id,
            )

    # 1. Resolve references in parameters (Session 22 - Helper #6)
    # BugFix 2025-11-30: Pass accumulated_registry for items[N].field resolution
    resolved_args, error_result = _resolve_step_references(
        step=step,
        completed_steps=completed_steps,
        context=context,
        start_time=start_time,
        wave_id=wave_id,
        registry=accumulated_registry,
    )
    if error_result:
        return error_result

    # 2. Get tool manifest from registry (Session 22 - Helper #7)
    _manifest, error_result = _get_tool_manifest_for_step(
        step=step,
        resolved_args=resolved_args,
        start_time=start_time,
        wave_id=wave_id,
    )
    if error_result:
        return error_result

    # 3. Type coercion (match tool schema)
    try:
        tool_registry = ToolRegistry.get_instance()
        try:
            tool = tool_registry.get_tool(step.tool_name)
        except (KeyError, ValueError):
            # Fallback: MCP tools with hallucinated suffix (evolution F2.1/F2.5)
            from src.core.context import (
                strip_hallucinated_mcp_suffix,
                user_mcp_tools_ctx,
            )

            tool = None

            # 1. Admin MCP: strip suffix and retry central registry
            stripped = strip_hallucinated_mcp_suffix(step.tool_name)
            if stripped:
                try:
                    tool = tool_registry.get_tool(stripped)
                    step.tool_name = stripped
                except (KeyError, ValueError):
                    pass

            # 2. User MCP: ContextVar with fuzzy resolve
            if tool is None:
                user_ctx = user_mcp_tools_ctx.get()
                if user_ctx:
                    resolved = user_ctx.resolve_tool_name(step.tool_name)
                    if resolved and resolved in user_ctx.tool_instances:
                        if resolved != step.tool_name:
                            step.tool_name = resolved
                        tool = user_ctx.tool_instances[resolved]

            if tool is None:
                raise
        tool_schema = tool.get_input_schema()
        resolved_args = _coerce_args_to_schema(resolved_args, tool_schema)
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        logger.warning(
            "type_coercion_failed",
            step_id=step.step_id,
            tool=step.tool_name,
            args=resolved_args,
            error=str(e),
            error_type=type(e).__name__,
        )
        # Continue without coercion - let Pydantic validate

    # =========================================================================
    # 3.5 SEMANTIC VALIDATION: Check required params are not empty after Jinja
    # =========================================================================
    # Problem: Jinja templates may evaluate to empty string when:
    # - No data matches the condition ({% if count > 1 %} with count=0)
    # - Referenced step has no items (steps.search.contacts is empty)
    # - GROUP operation returns no groups with count > 1
    #
    # Solution: Fail fast with clear error instead of calling tool with empty param.
    # This prevents confusing errors from tools and helps debug template issues.
    #
    # Architecture (2026-01-02): Supports AND and OR validation modes:
    # - list[str]: AND - all must be present (e.g., send_email: ["to", "subject", "body"])
    # - {"one_of": [...]}: OR - at least one (e.g., get_email_details: message_id OR message_ids)
    # =========================================================================
    is_valid, error_msg = _validate_required_params(step.tool_name, resolved_args)
    if not is_valid:
        logger.error(
            "semantic_validation_failed",
            step_id=step.step_id,
            tool_name=step.tool_name,
            all_args=resolved_args,
            error=error_msg,
        )
        execution_time_ms = int((time.time() - start_time) * 1000)
        return StepResult(
            step_id=step.step_id,
            step_type=StepType.TOOL,
            tool_name=step.tool_name,
            args=resolved_args,
            result={
                "success": False,
                "error": error_msg,
                FIELD_ERROR_CODE: ToolErrorCode.INVALID_INPUT.value,
            },
            success=False,
            error=error_msg,
            error_code=ToolErrorCode.INVALID_INPUT,
            execution_time_ms=execution_time_ms,
            wave_id=wave_id,
        )

    # 4. Execute tool directly
    # NOTE: HITL for planner should happen at PLAN VALIDATION level, not per-step execution
    # Direct tool calls bypass agent middleware intentionally for planner efficiency
    # TODO Phase 5.3: Implement plan-level HITL approval before execution starts
    # INTELLIA LocalQueryEngine: Pass accumulated_registry for local_query_engine_tool injection
    # BugFix 2025-12-19: Pass turn_id for RegistryItem.meta injection
    # Correlated Display: Pass step_id for RegistryItem.meta injection
    tool_execution_result = await _execute_tool(
        tool_name=step.tool_name,
        args=resolved_args,
        config=config,
        store=store,
        accumulated_registry=accumulated_registry,
        turn_id=turn_id,
        step_id=step.step_id,
    )

    # Data Registry LOT 5.2: Extract result and registry_updates from ToolExecutionResult
    tool_result = tool_execution_result.result
    registry_updates = tool_execution_result.registry_updates
    # Data Registry LOT 4.3: Extract draft_info if tool requires confirmation
    draft_info = tool_execution_result.draft_info

    # Enrich draft_info with step context
    if draft_info:
        draft_info["step_id"] = step.step_id

    # 6. Extract result fields
    success = tool_result.get("success", False)
    error = tool_result.get("error")
    # Normalize error to str (MCP servers may return error as dict e.g. {"message": "...", "type": "..."})
    if isinstance(error, dict):
        error = error.get("message") or str(error)
    elif error is not None and not isinstance(error, str):
        error = str(error)
    error_code = tool_result.get(FIELD_ERROR_CODE)

    execution_time_ms = int((time.time() - start_time) * 1000)

    return StepResult(
        step_id=step.step_id,
        step_type=StepType.TOOL,
        tool_name=step.tool_name,
        args=resolved_args,
        result=tool_result,
        success=success,
        error=error,
        error_code=ToolErrorCode(error_code) if error_code else None,
        execution_time_ms=execution_time_ms,
        wave_id=wave_id,
        # Data Registry LOT 5.2: Propagate registry_updates from registry-enabled tools
        registry_updates=registry_updates,
        # Data Registry LOT 4.3: Propagate draft_info if requires_confirmation=True
        draft_info=draft_info,
    )


class ToolExecutionResult(BaseModel):
    """
    Internal result type for tool execution with data registry support.

    Data Registry LOT 5.2: Captures both the tool result and any registry updates
    from StandardToolOutput returned by registry-enabled tools.

    Data Registry LOT 4.3: Captures draft info when requires_confirmation=True.

    Attributes:
        result: Tool result dict (ToolResponse format)
        registry_updates: Optional data registry items from StandardToolOutput
        draft_info: Draft details if tool returned requires_confirmation=True
    """

    result: dict[str, Any]
    registry_updates: dict[str, Any] | None = None
    draft_info: dict[str, Any] | None = None  # Data Registry LOT 4.3: Draft requiring confirmation


async def _execute_tool(
    tool_name: str,
    args: dict[str, Any],
    config: RunnableConfig,
    store: Any,
    accumulated_registry: dict[str, Any] | None = None,
    turn_id: int | None = None,
    step_id: str | None = None,
) -> ToolExecutionResult:
    """
    Execute a LangChain tool with ToolRuntime injection.

    Session 22: Refactored with 2 helpers (162 → ~77 lines, -52%).
    Data Registry LOT 5.2: Detects StandardToolOutput and extracts registry updates.
    INTELLIA LocalQueryEngine: Injects accumulated_registry for local_query_engine_tool.
    BugFix 2025-12-19: Injects turn_id into RegistryItem.meta for context resolution.
    Correlated Display: Injects step_id and correlated_to into RegistryItem.meta.

    Args:
        tool_name: Tool name
        args: Resolved arguments
        config: RunnableConfig with user_id, thread_id, store
        store: AsyncPostgresStore for context management
        accumulated_registry: INTELLIA LocalQueryEngine - registry items to inject
        turn_id: Current turn ID to inject into RegistryItem.meta (for context resolution)
        step_id: Execution plan step ID to inject into RegistryItem.meta (for correlated display)

    Returns:
        ToolExecutionResult with result dict and optional registry_updates
    """
    # Get tool from registry
    try:
        tool_registry = ToolRegistry.get_instance()
        tool = tool_registry.get_tool(tool_name)
    except (KeyError, ValueError, AttributeError, RuntimeError) as e:
        # Fallback: check user MCP tools ContextVar (evolution F2.1)
        from src.core.context import user_mcp_tools_ctx

        user_ctx = user_mcp_tools_ctx.get()
        if user_ctx and tool_name in user_ctx.tool_instances:
            tool = user_ctx.tool_instances[tool_name]
        else:
            return ToolExecutionResult(
                result={
                    "success": False,
                    "error": f"Tool '{tool_name}' not found: {e!s}",
                    FIELD_ERROR_CODE: ToolErrorCode.NOT_FOUND.value,
                }
            )

    # Build ToolRuntime and inject if needed (Session 22 - Helper #4)
    args = _build_tool_runtime(tool, args, config, store)

    # Correlated Display: Extract system parameter before tool execution
    # This is propagated from FOR_EACH expansion in dependency_graph.py
    correlation_parent_id = args.pop(FIELD_CORRELATION_PARENT_ID, None)
    if correlation_parent_id:
        logger.info(
            "correlation_parent_id_received",
            tool_name=tool_name,
            correlation_parent_id=correlation_parent_id,
        )

    # INTELLIA LocalQueryEngine: Inject accumulated_registry for local_query_engine_tool
    # This allows the tool to query data from previous steps without external API calls
    if tool_name == TOOL_LOCAL_QUERY_ENGINE and accumulated_registry is not None:
        # Convert registry dict values to list for QueryExecutor
        registry_items = list(accumulated_registry.values())
        args["injected_registry_items"] = registry_items
        logger.debug(
            "local_query_engine_registry_injected",
            tool_name=tool_name,
            registry_items_count=len(registry_items),
        )

    # Build ToolCall format for tool.ainvoke()
    from langchain_core.messages import ToolCall

    tool_call = ToolCall(
        name=tool_name,
        args=args,
        id=f"call_{tool_name}",  # Dummy ID
        type="tool_call",
    )

    try:
        # ============================================================================
        # BUGFIX (2025-11-26): Direct coroutine call to preserve StandardToolOutput.
        # LangChain's tool.ainvoke() converts results to ToolMessage(content=str(result)),
        # losing the StandardToolOutput object.
        #
        # Solution: Call tool.coroutine(**args) directly for async tools.
        # This bypasses LangChain's result conversion and preserves StandardToolOutput.
        #
        # 2025-12-29: Added UnifiedToolOutput support (new unified format).
        # UnifiedToolOutput has compatibility properties (summary_for_llm, tool_metadata)
        # so existing code continues to work.
        # ============================================================================
        from src.domains.agents.tools.output import StandardToolOutput, UnifiedToolOutput

        # Check if tool has async coroutine (StructuredTool from @tool decorator)
        if hasattr(tool, "coroutine") and tool.coroutine is not None:
            # Strip hallucinated parameters the LLM invented (e.g., "order", "order_by").
            # Without this, tool.coroutine(**args) raises TypeError and the entire
            # plan fails silently. Defense in depth — the planner should not hallucinate
            # params, but when it does, we strip them instead of crashing.
            import inspect

            sig = inspect.signature(tool.coroutine)
            valid_params = set(sig.parameters.keys())
            has_var_keyword = any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            )
            if not has_var_keyword:
                unknown_args = set(args.keys()) - valid_params
                if unknown_args:
                    logger.warning(
                        "tool_hallucinated_params_stripped",
                        tool_name=tool_name,
                        stripped_params=sorted(unknown_args),
                    )
                    args = {k: v for k, v in args.items() if k in valid_params}

            # Direct coroutine call - preserves StandardToolOutput!
            result = await tool.coroutine(**args)

            logger.debug(
                "tool_direct_coroutine_call",
                tool_name=tool_name,
                result_type=type(result).__name__,
                is_registry_output=isinstance(result, StandardToolOutput | UnifiedToolOutput),
            )
        else:
            # Fallback to ainvoke for sync tools or non-StructuredTool
            result = await tool.ainvoke(tool_call, config)

            logger.debug(
                "tool_ainvoke_fallback",
                tool_name=tool_name,
                result_type=type(result).__name__,
            )

        # Data Registry LOT 5.2: Check if tool returned StandardToolOutput or UnifiedToolOutput
        # Both have registry_updates that need to be propagated
        # UnifiedToolOutput has compatibility properties (summary_for_llm, tool_metadata)
        if isinstance(result, StandardToolOutput | UnifiedToolOutput):
            # Registry-enabled tool: Extract registry and use summary_for_llm
            # BugFix 2025-12-19: Inject turn_id into each item's meta for context resolution
            # Correlated Display: Inject step_id and correlated_to into each item's meta
            registry_updates = {}
            for item_id, item in result.registry_updates.items():
                item_dict = item.model_dump(mode="json")
                if isinstance(item_dict.get("meta"), dict):
                    # Inject turn_id if not already set
                    if turn_id is not None and item_dict["meta"].get("turn_id") is None:
                        item_dict["meta"]["turn_id"] = turn_id
                    # Inject step_id if not already set
                    if step_id is not None and item_dict["meta"].get(FIELD_STEP_ID) is None:
                        item_dict["meta"][FIELD_STEP_ID] = step_id
                    # Inject correlated_to if parent ID available (from FOR_EACH expansion)
                    if correlation_parent_id and item_dict["meta"].get(FIELD_CORRELATED_TO) is None:
                        item_dict["meta"][FIELD_CORRELATED_TO] = correlation_parent_id
                        logger.info(
                            "correlated_to_injected",
                            item_id=item_id,
                            correlation_parent_id=correlation_parent_id,
                            tool_name=tool_name,
                        )
                registry_updates[item_id] = item_dict

            # Data Registry LOT 4.3: Check for draft requiring confirmation
            draft_info = None
            if result.tool_metadata.get("requires_confirmation"):
                draft_id = result.tool_metadata.get("draft_id")
                draft_type = result.tool_metadata.get("draft_type")

                # Extract draft content from registry
                draft_content = {}
                if draft_id and draft_id in result.registry_updates:
                    draft_item = result.registry_updates[draft_id]
                    draft_content = draft_item.payload.get("content", {})

                draft_info = {
                    "draft_id": draft_id,
                    "draft_type": draft_type,
                    "draft_content": draft_content,
                    "draft_summary": result.summary_for_llm,
                    "registry_ids": list(result.registry_updates.keys()),
                    "tool_name": tool_name,
                }

                logger.info(
                    "registry_draft_detected_requires_confirmation",
                    tool_name=tool_name,
                    draft_id=draft_id,
                    draft_type=draft_type,
                    registry_items_count=len(registry_updates),
                )
            else:
                logger.info(
                    "registry_tool_output_detected",
                    tool_name=tool_name,
                    registry_items_count=len(registry_updates),
                    summary_length=len(result.summary_for_llm),
                )

            # =================================================================
            # Data Registry LOT 5.3 FIX: Expose structured data for Jinja templates
            # =================================================================
            # Problem: completed_steps only contained summary_for_llm (string).
            # Jinja templates like `{% for c in steps.search.contacts %}` failed
            # because there was no `.contacts` array - just `.result` string.
            #
            # Solution: Extract contacts/emails from registry_updates and expose
            # them in the result data. This allows Jinja templates to iterate
            # over structured data while LLM still sees the summary.
            # =================================================================
            structured_data: dict[str, Any] = {
                FIELD_RESULT: result.summary_for_llm,
            }

            # =================================================================
            # GENERIC: Extract ALL registry item types for Jinja access
            # =================================================================
            # Design: Group items by meta.domain (the canonical result_key).
            # The meta.domain value comes from CONTEXT_DOMAIN_* constants which
            # are aligned with DomainConfig.result_key in domain_taxonomy.py.
            #
            # This is the SINGLE source of truth for naming - no more conversions!
            # Examples: meta.domain="contacts" → structured_data["contacts"]
            #           meta.domain="weathers" → structured_data["weathers"]
            # =================================================================
            items_by_domain: dict[str, list[dict[str, Any]]] = {}

            for item_id, item_dict in registry_updates.items():
                payload = item_dict.get("payload", {})
                meta = item_dict.get("meta", {})
                # Use meta.domain as the canonical key (aligned with result_key)
                # Fallback to item_type.lower() + "s" for legacy items without meta.domain
                item_type = item_dict.get("type", "")
                key = meta.get("domain") or (item_type.lower() + "s" if item_type else "unknown")

                if payload:
                    if key not in items_by_domain:
                        items_by_domain[key] = []

                    # Add registry_id to payload for Jinja reference
                    enriched_payload = {**payload, FIELD_REGISTRY_ID: item_id}
                    items_by_domain[key].append(enriched_payload)

            # Expose all domains in structured_data for Jinja templates
            for key, items in items_by_domain.items():
                structured_data[key] = items
                logger.debug(
                    "registry_exposed_items_for_jinja",
                    tool_name=tool_name,
                    domain_key=key,
                    count=len(items),
                )

            # =================================================================
            # evolution F2.4: Gentle merge of tool-provided structured_data
            # =================================================================
            # Tools (notably UserMCPToolAdapter) can set structured_data with
            # additional keys (e.g. "repositories") that the registry derivation
            # above does not produce.  We merge them here **without overwriting**
            # any registry-derived key, preserving the enriched payloads
            # (which carry _registry_id for parent correlation in for_each).
            #
            # Verified safe: no existing native tool has key conflicts with
            # registry-derived domain keys.
            # =================================================================
            if isinstance(result, UnifiedToolOutput) and result.structured_data:
                for key, value in result.structured_data.items():
                    if key not in structured_data:
                        structured_data[key] = value

            # =================================================================
            # FIX Issue #dupond-15h55: Expose groups for LocalQueryEngine GROUP
            # =================================================================
            # Problem: Planner generates Jinja templates like:
            #   {% for group in steps.group_by_address.query_result %}
            # But groups were not exposed in structured_data for Jinja access.
            #
            # Solution: Extract "groups" from tool_metadata (set by local_query_tool)
            # and add to structured_data so Jinja templates can access them.
            #
            # FIX Issue #dupond-16h57: Add query_result alias
            # The planner uses "query_result" not "groups" in Jinja templates.
            # Expose both names for compatibility.
            # =================================================================
            if result.tool_metadata:
                # GROUP operation: expose groups list
                if "groups" in result.tool_metadata:
                    groups_data = result.tool_metadata["groups"]
                    # =================================================================
                    # FIX: Extract payloads from RegistryItem objects in group.members
                    # =================================================================
                    # Problem: groups_data contains groups where "members" are RegistryItem
                    # objects (or dicts with {id, type, payload, meta}). Jinja templates
                    # like {{ item.resource_name }} fail because resource_name is inside
                    # payload, not at top level.
                    #
                    # Solution: Transform members to extract payloads, consistent with
                    # how contacts_list is built above (lines 2229-2232).
                    # This allows {{ item.resource_name }} to work in Jinja templates.
                    # =================================================================
                    transformed_groups = []
                    for group in groups_data:
                        transformed_members = []
                        for item in group.get("members", []):
                            # Extract payload from RegistryItem (object or dict)
                            if hasattr(item, "payload"):
                                # Pydantic RegistryItem object
                                payload = item.payload
                                item_id = item.id
                            elif isinstance(item, dict) and "payload" in item:
                                # Serialized RegistryItem dict
                                payload = item["payload"]
                                item_id = item.get("id", "")
                            else:
                                # Already a payload dict (fallback)
                                payload = item
                                item_id = item.get(FIELD_REGISTRY_ID, "")

                            if payload:
                                # Add registry_id for reference (consistent with contacts_list)
                                enriched_payload = {**payload, FIELD_REGISTRY_ID: item_id}
                                transformed_members.append(enriched_payload)

                        transformed_groups.append(
                            {
                                "key": group.get("key", ""),
                                "members": transformed_members,
                                "count": len(transformed_members),
                            }
                        )

                    structured_data["groups"] = transformed_groups
                    # CRITICAL: Planner generates templates with .query_result, not .groups
                    structured_data["query_result"] = transformed_groups
                    logger.debug(
                        "registry_exposed_groups_for_jinja",
                        tool_name=tool_name,
                        groups_count=len(transformed_groups),
                        aliases=["groups", "query_result"],
                        sample_group_keys=[g["key"] for g in transformed_groups[:3]],
                    )
                # AGGREGATE operation: expose distinct_values
                if "distinct_values" in result.tool_metadata:
                    structured_data["distinct_values"] = result.tool_metadata["distinct_values"]
                    logger.debug(
                        "registry_exposed_distinct_values_for_jinja",
                        tool_name=tool_name,
                        distinct_count=len(result.tool_metadata["distinct_values"]),
                    )

            # Propagate TCM flag and save mode so _auto_save_wave_contexts can
            # detect decorator-saved tools and skip the duplicate save path.
            tcm_saved = (
                result.tool_metadata.get("_tcm_saved", False) if result.tool_metadata else False
            )
            save_mode_value = (
                result.context_save_mode.value
                if result.context_save_mode is not None
                and hasattr(result.context_save_mode, "value")
                else result.context_save_mode
            )

            return ToolExecutionResult(
                result={
                    "success": True,
                    "data": structured_data,
                    "message": result.summary_for_llm,
                    "_tcm_saved": tcm_saved,
                    "context_save_mode": save_mode_value,
                },
                registry_updates=registry_updates,
                draft_info=draft_info,
            )

        # Legacy tool: Parse tool result (Session 22 - Helper #5)
        return ToolExecutionResult(result=_parse_tool_result(result))

    except (
        TimeoutError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        asyncio.CancelledError,
        OSError,
    ) as e:
        logger.error(
            "tool_execution_failed",
            tool=tool_name,
            args=args,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return ToolExecutionResult(
            result={
                "success": False,
                "error": f"Tool execution failed: {e!s}",
                FIELD_ERROR_CODE: ToolErrorCode.INTERNAL_ERROR.value,
            }
        )


def _coerce_args_to_schema(args: dict[str, Any], tool_schema: type) -> dict[str, Any]:
    """
    Coerce argument types to match tool schema.

    Issue #53 FIX: Added coercion for comma-separated strings to lists.
    Issue #55 FIX: Robust handling of LLM-generated separator patterns.

    Uses shared coercion utilities from type_coercion module (DRY principle).

    Args:
        args: Resolved arguments
        tool_schema: Tool input schema (Pydantic BaseModel)

    Returns:
        Arguments with coerced types
    """
    from pydantic import BaseModel

    from src.domains.agents.orchestration.type_coercion import (
        coerce_string_to_list,
        is_list_type,
    )

    if not issubclass(tool_schema, BaseModel):
        return args

    # Get field types from schema
    field_types = {name: field.annotation for name, field in tool_schema.model_fields.items()}

    coerced = {}
    for key, value in args.items():
        if key not in field_types:
            coerced[key] = value
            continue

        expected_type = field_types[key]

        # Coerce int → str
        if expected_type is str and isinstance(value, int):
            coerced[key] = str(value)
        # Coerce float → int
        elif expected_type is int and isinstance(value, float):
            coerced[key] = int(value)
        # Issue #53 + #55 FIX: Coerce string → list with robust separator handling
        elif is_list_type(expected_type) and isinstance(value, str):
            coerced[key] = coerce_string_to_list(value)
        # MCP FIX: Coerce list/dict → JSON string when tool expects str.
        # LLMs generating plans often produce JSON arrays/objects natively
        # instead of escaped JSON strings (e.g., Excalidraw elements parameter).
        elif expected_type is str and isinstance(value, list | dict):
            coerced[key] = json.dumps(value)
            logger.debug(
                "type_coercion_json_to_str",
                key=key,
                original_type=type(value).__name__,
                json_length=len(coerced[key]),
            )
        else:
            coerced[key] = value

    return coerced


# ============================================================================
# Conditional Step Execution
# ============================================================================


async def _execute_conditional_step(
    step: ExecutionStep,
    completed_steps: dict[str, dict[str, Any]],
    wave_id: int,
) -> StepResult:
    """
    Execute a CONDITIONAL step.

    Copied from step_executor_node._execute_conditional_step().

    Args:
        step: ExecutionStep with step_type=CONDITIONAL
        completed_steps: Map of step_id -> result data
        wave_id: Current wave number

    Returns:
        StepResult with condition_result field
    """
    start_time = time.time()
    evaluator = ConditionEvaluator()

    if not step.condition:
        execution_time_ms = int((time.time() - start_time) * 1000)
        return StepResult(
            step_id=step.step_id,
            step_type=StepType.CONDITIONAL,
            success=False,
            error="CONDITIONAL step missing condition field",
            error_code=ToolErrorCode.INVALID_INPUT,
            execution_time_ms=execution_time_ms,
            wave_id=wave_id,
        )

    try:
        condition_result = evaluator.evaluate(step.condition, completed_steps)

        execution_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "conditional_evaluated",
            step_id=step.step_id,
            condition=step.condition,
            result=condition_result,
            on_success=step.on_success,
            on_fail=step.on_fail,
            execution_time_ms=execution_time_ms,
        )

        return StepResult(
            step_id=step.step_id,
            step_type=StepType.CONDITIONAL,
            condition_result=condition_result,
            success=True,
            execution_time_ms=execution_time_ms,
            wave_id=wave_id,
        )

    except (ValueError, KeyError) as e:
        execution_time_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "conditional_evaluation_failed",
            step_id=step.step_id,
            condition=step.condition,
            error=str(e),
            exc_info=True,
        )
        return StepResult(
            step_id=step.step_id,
            step_type=StepType.CONDITIONAL,
            success=False,
            error=f"Condition evaluation failed: {e!s}",
            error_code=ToolErrorCode.INVALID_INPUT,
            execution_time_ms=execution_time_ms,
            wave_id=wave_id,
        )


# ============================================================================
# Result Merging
# ============================================================================


def _merge_single_step_result(
    completed_steps: dict[str, dict[str, Any]],
    step_result: StepResult,
    accumulated_registry: dict[str, Any] | None = None,
    accumulated_drafts: list[dict[str, Any]] | None = None,
    current_turn_touched_ids: set[str] | None = None,
) -> None:
    """
    Merge a single StepResult into completed_steps (in-place).

    Copied/adapted from wave_aggregator_node._merge_step_results().

    Data Registry LOT 5.2: Also accumulates registry_updates from registry-enabled tools.
    Data Registry LOT 4.3: Also collects draft_info from tools requiring confirmation.

    Args:
        completed_steps: Accumulated results (modified in-place)
        step_result: Result to merge
        accumulated_registry: Optional dict to accumulate data registry items (modified in-place)
        accumulated_drafts: Optional list to accumulate draft_info from registry draft tools (modified in-place)
        current_turn_touched_ids: Optional set to track IDs added/updated this turn (modified in-place)

    Note:
        - TOOL steps: Extract result.data
        - CONDITIONAL steps: Store condition_result for routing
        - Failed steps: Store with success=False
        - Registry tools: Accumulate registry_updates in accumulated_registry
        - Draft tools: Accumulate draft_info in accumulated_drafts
    """
    # Data Registry LOT 5.2: Accumulate registry updates if present
    # BugFix 2025-12-01 v2: Track ALL IDs from this step's registry_updates
    # This includes both NEW items and UPDATED items (e.g., get_contact_details enriching search results)
    if accumulated_registry is not None and step_result.registry_updates:
        accumulated_registry.update(step_result.registry_updates)
        # Track all IDs from this step (new or updated)
        if current_turn_touched_ids is not None:
            current_turn_touched_ids.update(step_result.registry_updates.keys())
        logger.debug(
            "registry_accumulated",
            step_id=step_result.step_id,
            registry_items_count=len(step_result.registry_updates),
            total_registry_size=len(accumulated_registry),
            touched_ids=list(step_result.registry_updates.keys()),
        )

    # Data Registry LOT 4.3: Accumulate draft info if present
    if accumulated_drafts is not None and step_result.draft_info:
        accumulated_drafts.append(step_result.draft_info)
        logger.info(
            "registry_draft_accumulated",
            step_id=step_result.step_id,
            draft_id=step_result.draft_info.get("draft_id"),
            draft_type=step_result.draft_info.get("draft_type"),
            total_drafts_count=len(accumulated_drafts),
        )

    if step_result.step_type == StepType.TOOL:
        # TOOL step: Extract data from result
        if step_result.success:
            # INTELLIPLANNER B+: Prioritize structured_data for Jinja2 templates
            if step_result.structured_data:
                completed_steps[step_result.step_id] = step_result.structured_data
                logger.debug(
                    "step_merged_with_structured_data",
                    step_id=step_result.step_id,
                    structured_data_keys=list(step_result.structured_data.keys()),
                )
            elif step_result.result:
                # Fallback: Extract data field or use entire result (legacy)
                data = step_result.result.get("data", step_result.result)
                completed_steps[step_result.step_id] = data
                logger.debug(
                    "step_merged_with_result_data_fallback",
                    step_id=step_result.step_id,
                )
            else:
                completed_steps[step_result.step_id] = {"success": True}
        else:
            # Failed TOOL: Store error info
            completed_steps[step_result.step_id] = {
                "success": False,
                "error": step_result.error,
                FIELD_ERROR_CODE: step_result.error_code.value if step_result.error_code else None,
            }

    elif step_result.step_type == StepType.CONDITIONAL:
        # CONDITIONAL step: Store condition result for routing
        if step_result.success:
            completed_steps[step_result.step_id] = {
                "condition_result": step_result.condition_result,
                "success": True,
            }
        else:
            # Failed CONDITIONAL: Store error
            completed_steps[step_result.step_id] = {
                "success": False,
                "error": step_result.error,
            }

    else:
        # Unknown step type (should not happen)
        logger.warning(
            "unknown_step_type_in_results",
            step_id=step_result.step_id,
            step_type=step_result.step_type.value,
        )
        completed_steps[step_result.step_id] = {"success": False, "error": "Unknown step type"}


def _aggregate_for_each_results(
    completed_steps: dict[str, dict[str, Any]],
    original_step_id: str,
    expanded_step_ids: list[str],
) -> None:
    """
    Aggregate results from FOR_EACH expanded steps under the original step_id.

    After FOR_EACH expansion, step_2 becomes step_2_item_0, step_2_item_1, etc.
    Downstream steps may still reference $steps.step_2.places in their parameters.
    This function creates an aggregated result under the original step_id to
    enable these parameter references to resolve correctly.

    Args:
        completed_steps: Results from completed steps (modified in-place)
        original_step_id: The original FOR_EACH step_id (e.g., "step_2")
        expanded_step_ids: List of expanded step_ids (e.g., ["step_2_item_0", "step_2_item_1"])

    Example:
        Before:
            completed_steps["step_2_item_0"] = {"places": [place_a, place_b]}
            completed_steps["step_2_item_1"] = {"places": [place_c, place_d]}

        After:
            completed_steps["step_2"] = {"places": [place_a, place_b, place_c, place_d]}

    Algorithm:
        1. Collect all expanded step results
        2. For keys with list values: concatenate all lists
        3. For other keys: use value from last expanded step
        4. Store aggregated result under original_step_id
    """
    if not expanded_step_ids:
        logger.debug(
            "for_each_aggregation_skipped_empty",
            original_step_id=original_step_id,
            reason="No expanded steps to aggregate",
        )
        return

    # Collect results from all expanded steps
    expanded_results: list[dict[str, Any]] = []
    for exp_id in expanded_step_ids:
        if exp_id in completed_steps:
            expanded_results.append(completed_steps[exp_id])

    if not expanded_results:
        logger.warning(
            "for_each_aggregation_no_results",
            original_step_id=original_step_id,
            expanded_step_ids=expanded_step_ids,
            reason="No expanded step results found in completed_steps",
        )
        return

    # Aggregate: merge list values, collect action messages, keep last value for others
    aggregated: dict[str, Any] = {}

    # First pass: identify all keys and their types
    all_keys: set[str] = set()
    for result in expanded_results:
        all_keys.update(result.keys())

    # Second pass: aggregate each key
    for key in all_keys:
        values = [result.get(key) for result in expanded_results if key in result]

        if not values:
            continue

        # Check if all values are lists
        if all(isinstance(v, list) for v in values):
            # Concatenate all lists
            merged_list: list[Any] = []
            for v in values:
                merged_list.extend(v)
            aggregated[key] = merged_list
        elif key == FIELD_RESULT and all(isinstance(v, str) for v in values if v is not None):
            # BugFix 2026-01-22: Collect ALL action confirmation messages into a list
            # FOR_EACH expansion creates multiple steps, each with a "result" string message
            # (e.g., "Reminder created for..."). Previously, only the LAST value was kept.
            # Now we collect all non-None string values so response_node can show all messages.
            non_none_values = [v for v in values if v is not None]
            if len(non_none_values) > 1:
                aggregated[key] = non_none_values  # List of all messages
            elif non_none_values:
                aggregated[key] = non_none_values[0]  # Single message, keep as string
        else:
            # Use last non-None value
            for v in reversed(values):
                if v is not None:
                    aggregated[key] = v
                    break

    # Store aggregated result under original step_id
    completed_steps[original_step_id] = aggregated

    logger.info(
        "for_each_results_aggregated",
        original_step_id=original_step_id,
        expanded_count=len(expanded_step_ids),
        aggregated_keys=list(aggregated.keys()),
        list_keys=[k for k, v in aggregated.items() if isinstance(v, list)],
    )


# ============================================================================
# CONDITIONAL Branching Support
# ============================================================================


def _identify_skipped_steps(
    execution_plan: ExecutionPlan,
    completed_steps: dict[str, dict[str, Any]],
) -> set[str]:
    """
    Identify steps that should be skipped due to CONDITIONAL branching.

    Copied from wave_aggregator_node._identify_skipped_steps().

    Args:
        execution_plan: The execution plan being executed
        completed_steps: Steps completed so far (includes CONDITIONAL results)

    Returns:
        Set of step_ids that should be skipped (not required for completion)
    """
    skipped = set()
    steps_by_id = {step.step_id: step for step in execution_plan.steps}

    # Find all CONDITIONAL steps that have been completed
    for step_id, step_data in completed_steps.items():
        step = steps_by_id.get(step_id)

        if not step or step.step_type != StepType.CONDITIONAL:
            continue

        # CONDITIONAL step completed - determine which branch was taken
        condition_result = step_data.get("condition_result")

        if condition_result is True:
            # on_success branch taken → skip on_fail branch
            if step.on_fail:
                skipped.update(_collect_branch_steps(step.on_fail, steps_by_id, completed_steps))
        elif condition_result is False:
            # on_fail branch taken → skip on_success branch
            if step.on_success:
                skipped.update(_collect_branch_steps(step.on_success, steps_by_id, completed_steps))
        else:
            # CONDITIONAL step failed or condition_result not set
            logger.warning(
                "conditional_step_no_result",
                step_id=step_id,
                step_data=step_data,
                message="CONDITIONAL step completed but condition_result not set",
            )

    return skipped


def _collect_branch_steps(
    start_step_id: str,
    steps_by_id: dict[str, Any],
    completed_steps: dict[str, dict[str, Any]],
    visited: set[str] | None = None,
) -> set[str]:
    """
    Recursively collect all steps in a branch starting from start_step_id.

    Copied from wave_aggregator_node._collect_branch_steps().

    Args:
        start_step_id: The first step in the branch to skip
        steps_by_id: Lookup dict of all steps
        completed_steps: Steps completed so far
        visited: Set of already visited step_ids (prevents infinite loops)

    Returns:
        Set of all step_ids in this branch (including nested branches)
    """
    if visited is None:
        visited = set()

    if start_step_id in visited or start_step_id not in steps_by_id:
        return set()

    visited.add(start_step_id)
    branch_steps = {start_step_id}

    # Don't recurse into steps that were actually executed
    if start_step_id in completed_steps:
        return branch_steps

    # Find all steps that depend on this step
    start_step = steps_by_id[start_step_id]

    # If this is a CONDITIONAL, add both branches
    if start_step.step_type == StepType.CONDITIONAL:
        if start_step.on_success:
            branch_steps.update(
                _collect_branch_steps(start_step.on_success, steps_by_id, completed_steps, visited)
            )
        if start_step.on_fail:
            branch_steps.update(
                _collect_branch_steps(start_step.on_fail, steps_by_id, completed_steps, visited)
            )

    # Find steps that explicitly depend on this step
    for step_id, step in steps_by_id.items():
        if start_step_id in step.depends_on:
            branch_steps.update(
                _collect_branch_steps(step_id, steps_by_id, completed_steps, visited)
            )

    return branch_steps


# ============================================================================
# FOR_EACH Execution Support (plan_planner.md Section 6-7)
# ============================================================================


async def _expand_and_execute_for_each_if_ready(
    execution_plan: ExecutionPlan,
    dep_graph: DependencyGraph,
    steps_by_id: dict[str, ExecutionStep],
    completed_steps: dict[str, dict[str, Any]],
    excluded_steps: set[str],
    config: RunnableConfig,
    store: Any,
    context: dict[str, Any],
    current_wave_id: int,
    run_id: str,
    accumulated_registry: dict[str, Any],
    accumulated_drafts: list[dict[str, Any]],
    current_turn_touched_ids: set[str],
    turn_id: int | None = None,
) -> tuple[ExecutionPlan, DependencyGraph, dict[str, ExecutionStep]] | None:
    """
    Check for FOR_EACH steps ready for expansion, expand and execute them.

    This is a DRY helper that encapsulates the complete FOR_EACH handling logic.
    Called at two points in execute_plan_parallel:
    1. BEFORE calculating next wave (handles initial_completed_steps case)
    2. AFTER executing a wave (handles normal flow)

    BugFix 2026-01-19: Created to avoid code duplication. The same logic was
    previously duplicated in two places, violating DRY principle.

    Args:
        execution_plan: Current ExecutionPlan
        dep_graph: Current DependencyGraph
        steps_by_id: Current step lookup dict
        completed_steps: Steps completed so far (modified in place)
        excluded_steps: Steps to exclude (skipped branches)
        config: RunnableConfig
        store: AsyncPostgresStore
        context: Conversation context
        current_wave_id: Current wave number (for logging)
        run_id: Run ID for logging
        accumulated_registry: Registry accumulator (modified in place)
        accumulated_drafts: Drafts accumulator (modified in place)
        current_turn_touched_ids: Set of IDs touched this turn (modified in place)
        turn_id: Current turn ID

    Returns:
        Tuple of (updated_plan, updated_dep_graph, updated_steps_by_id) if expansion
        occurred, None otherwise.
    """
    # Check for FOR_EACH steps ready for expansion
    for_each_steps_to_expand = [
        step
        for step in execution_plan.steps
        if step.is_for_each_step
        and step.step_id not in completed_steps
        and step.step_id not in excluded_steps
        and is_for_each_ready_for_expansion(step, completed_steps)
    ]

    if not for_each_steps_to_expand:
        return None

    logger.info(
        "for_each_expansion_triggered",
        run_id=run_id,
        wave_id=current_wave_id,
        steps_to_expand=[s.step_id for s in for_each_steps_to_expand],
    )

    # Expand FOR_EACH steps
    expanded_steps, expansion_map = dep_graph.expand_for_each_steps(completed_steps)

    # Log scope check (HITL already handled in task_orchestrator_node)
    for original_step in for_each_steps_to_expand:
        expanded_ids = expansion_map.get(original_step.step_id, [])
        iteration_count = len(expanded_ids)

        if iteration_count > 0:
            scope = detect_for_each_scope(
                iteration_count=iteration_count,
                tool_name=original_step.tool_name or "unknown",
                is_mutation=False,
                for_each_max=original_step.for_each_max,
            )

            if scope.requires_approval:
                logger.info(
                    "for_each_scope_check_at_execution",
                    run_id=run_id,
                    step_id=original_step.step_id,
                    tool_name=original_step.tool_name,
                    iteration_count=iteration_count,
                    is_mutation=scope.is_mutation,
                    risk_level=scope.risk_level.value,
                    reason=scope.reason,
                    for_each_max=original_step.for_each_max,
                    note="HITL already handled pre-execution in task_orchestrator_node",
                )
            else:
                logger.debug(
                    "for_each_hitl_not_required",
                    run_id=run_id,
                    step_id=original_step.step_id,
                    iteration_count=iteration_count,
                    risk_level=scope.risk_level.value,
                )

    # Execute expanded steps (respects delay_between_items_ms, on_item_error)
    for original_step in for_each_steps_to_expand:
        expanded_step_ids = expansion_map.get(original_step.step_id, [])
        if not expanded_step_ids:
            continue

        expanded_ids_set = set(expanded_step_ids)
        expanded_step_objs = [step for step in expanded_steps if step.step_id in expanded_ids_set]

        if not expanded_step_objs:
            continue

        results, errors = await _execute_for_each_wave(
            expanded_steps=expanded_step_objs,
            original_step=original_step,
            completed_steps=completed_steps,
            config=config,
            store=store,
            context=context,
            wave_id=current_wave_id,
            run_id=run_id,
            accumulated_registry=accumulated_registry,
            accumulated_drafts=accumulated_drafts,
            current_turn_touched_ids=current_turn_touched_ids,
            turn_id=turn_id,
        )

        # Merge results into completed_steps
        for result in results:
            _merge_single_step_result(
                completed_steps,
                result,
                accumulated_registry,
                accumulated_drafts,
                current_turn_touched_ids,
            )

        # Log errors if using collect_errors mode
        if errors and original_step.on_item_error == "collect_errors":
            logger.warning(
                "for_each_collected_errors",
                run_id=run_id,
                original_step_id=original_step.step_id,
                error_count=len(errors),
                errors=errors,
            )

        # Aggregate expanded results under original step_id for downstream parameter resolution
        # This enables $steps.step_2.places to resolve even after step_2 is expanded to step_2_item_N
        expanded_ids = expansion_map.get(original_step.step_id, [])
        _aggregate_for_each_results(
            completed_steps=completed_steps,
            original_step_id=original_step.step_id,
            expanded_step_ids=expanded_ids,
        )

    # Update execution_plan with expanded steps
    updated_plan = ExecutionPlan(
        user_id=execution_plan.user_id,
        session_id=execution_plan.session_id,
        plan_id=execution_plan.plan_id,
        execution_mode=execution_plan.execution_mode,
        steps=expanded_steps,
        metadata=execution_plan.metadata,
    )
    updated_steps_by_id = {step.step_id: step for step in updated_plan.steps}
    updated_dep_graph = DependencyGraph(updated_plan)

    logger.info(
        "for_each_expansion_completed",
        run_id=run_id,
        wave_id=current_wave_id,
        expansion_map=expansion_map,
        new_step_count=len(updated_plan.steps),
    )

    return updated_plan, updated_dep_graph, updated_steps_by_id


async def _execute_for_each_wave(
    expanded_steps: list[ExecutionStep],
    original_step: ExecutionStep,
    completed_steps: dict[str, dict[str, Any]],
    config: RunnableConfig,
    store: Any,
    context: dict[str, Any],
    wave_id: int,
    run_id: str,
    accumulated_registry: dict[str, Any] | None = None,
    accumulated_drafts: list[dict[str, Any]] | None = None,
    current_turn_touched_ids: set[str] | None = None,
    turn_id: int | None = None,
) -> tuple[list[StepResult], list[dict[str, Any]]]:
    """
    Execute for_each expanded steps with delay and error handling.

    This function handles the special execution of for_each expanded steps,
    respecting delay_between_items_ms and on_item_error settings from the
    original step.

    Args:
        expanded_steps: List of expanded steps (step_2_item_0, step_2_item_1, etc.)
        original_step: The original for_each step (for config: delay, on_item_error)
        completed_steps: Steps completed so far (for reference resolution)
        config: RunnableConfig with user_id, thread_id
        store: AsyncPostgresStore for tool context management
        context: Conversation context data
        wave_id: Current wave number
        run_id: Run ID for logging
        accumulated_registry: Optional dict to accumulate data registry items
        accumulated_drafts: Optional list to accumulate draft_info
        current_turn_touched_ids: Optional set to track IDs added/updated this turn
        turn_id: Current turn ID for RegistryItem.meta injection

    Returns:
        Tuple of:
        - List of StepResult objects (one per expanded step)
        - List of error details (for on_item_error="collect_errors")

    Behavior based on on_item_error:
        - "continue": Execute all items, ignore failures
        - "stop": Stop on first failure
        - "collect_errors": Execute all items, collect all errors for reporting
    """
    results: list[StepResult] = []
    collected_errors: list[dict[str, Any]] = []
    delay_ms = original_step.delay_between_items_ms
    error_mode = original_step.on_item_error

    logger.info(
        "for_each_wave_started",
        run_id=run_id,
        original_step_id=original_step.step_id,
        expanded_count=len(expanded_steps),
        delay_ms=delay_ms,
        error_mode=error_mode,
        wave_id=wave_id,
    )

    # If no delay, execute all in parallel (standard behavior)
    if delay_ms == 0:
        tasks = [
            _execute_single_step_async(
                step=step,
                completed_steps=completed_steps,
                config=config,
                wave_id=wave_id,
                store=store,
                context=context,
                accumulated_registry=accumulated_registry,
                turn_id=turn_id,
            )
            for step in expanded_steps
        ]
        # FIX 2026-02-06: Use return_exceptions=True for FOR_EACH parallel execution
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed StepResults
        results = []
        for i, result in enumerate(raw_results):
            if isinstance(result, Exception):
                step = expanded_steps[i]
                logger.error(
                    "for_each_step_exception",
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    error_type=type(result).__name__,
                    error_message=str(result),
                )
                results.append(
                    StepResult(
                        step_id=step.step_id,
                        step_type=step.step_type,
                        tool_name=step.tool_name,
                        success=False,
                        error=f"{type(result).__name__}: {result}",
                        error_code=ToolErrorCode.INTERNAL_ERROR,
                        execution_time_ms=0,
                        wave_id=wave_id,
                    )
                )
            else:
                results.append(result)

        # Handle error collection for on_item_error modes
        for result in results:
            if not result.success:
                error_info = {
                    "step_id": result.step_id,
                    "error": result.error,
                    "error_code": result.error_code,
                }
                collected_errors.append(error_info)

                if error_mode == "stop":
                    logger.warning(
                        "for_each_stopped_on_error",
                        run_id=run_id,
                        original_step_id=original_step.step_id,
                        failed_step_id=result.step_id,
                        error=result.error,
                    )
                    break
    else:
        # Execute with delay between items (sequential with throttling)
        for i, step in enumerate(expanded_steps):
            # Add delay before each step (except the first)
            if i > 0 and delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)

            result = await _execute_single_step_async(
                step=step,
                completed_steps=completed_steps,
                config=config,
                wave_id=wave_id,
                store=store,
                context=context,
                accumulated_registry=accumulated_registry,
                turn_id=turn_id,
            )
            results.append(result)

            if not result.success:
                error_info = {
                    "step_id": result.step_id,
                    "error": result.error,
                    "error_code": result.error_code,
                }
                collected_errors.append(error_info)

                if error_mode == "stop":
                    logger.warning(
                        "for_each_stopped_on_error_with_delay",
                        run_id=run_id,
                        original_step_id=original_step.step_id,
                        failed_step_id=result.step_id,
                        error=result.error,
                        completed_items=i + 1,
                        total_items=len(expanded_steps),
                    )
                    break

    # Log completion
    success_count = sum(1 for r in results if r.success)
    logger.info(
        "for_each_wave_completed",
        run_id=run_id,
        original_step_id=original_step.step_id,
        total_items=len(expanded_steps),
        executed_items=len(results),
        success_count=success_count,
        error_count=len(collected_errors),
        error_mode=error_mode,
        wave_id=wave_id,
    )

    return results, collected_errors


def _detect_for_each_steps(
    steps_by_id: dict[str, ExecutionStep],
) -> dict[str, ExecutionStep]:
    """
    Detect steps that use for_each pattern.

    Args:
        steps_by_id: Lookup dict of all steps {step_id: ExecutionStep}

    Returns:
        Dict of for_each steps {step_id: ExecutionStep}
    """
    return {step_id: step for step_id, step in steps_by_id.items() if step.is_for_each_step}


# NOTE: _get_for_each_provider_step_id and _is_for_each_ready_for_expansion
# have been moved to for_each_utils.py for DRY compliance.
# Import from: src.domains.agents.orchestration.for_each_utils
