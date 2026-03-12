"""
Business Metrics Calculation Service (Phase 3.2).

Calculates conversation-level business metrics for Prometheus tracking.
Separates calculation logic (complex) from instrumentation (simple).

Metrics calculated:
- Conversation cost (USD) from LLM token usage
- Total tokens consumed (prompt + completion)
- Conversation turns (user-agent exchanges)
- Conversation outcome (success/failure/abandoned/partial)
- Agent type extraction

Architecture:
- Pure calculation functions (no Prometheus calls)
- Async-ready for FastAPI routes
- Testable in isolation (no external dependencies)
- Graceful degradation (returns defaults on errors)

Best Practices 2025:
- Pydantic models for type safety
- Structured logging with context
- Named tuples for return values
- Comprehensive error handling
- Token efficiency tracking

Phase: 3.2 - Business Metrics
Date: 2025-11-23
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_MESSAGES,
    STATE_KEY_PLANNER_ERROR,
)
from src.domains.agents.models import MessagesState

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass(frozen=True)
class ConversationMetrics:
    """
    Business metrics for a completed conversation.

    Attributes:
        agent_type: Agent identifier (contacts, generic, emails)
        cost_usd: Total conversation cost in USD
        tokens_total: Total tokens (prompt + completion)
        turns: Number of user-agent turns
        outcome: Conversation outcome (success, failure, partial_success, abandoned)
        message_count: Total messages in conversation
        has_errors: Whether conversation encountered errors
    """

    agent_type: str
    cost_usd: float
    tokens_total: int
    turns: int
    outcome: str  # success, failure, partial_success, abandoned
    message_count: int
    has_errors: bool


# ============================================================================
# METRICS CALCULATION FUNCTIONS
# ============================================================================


def calculate_conversation_metrics(
    state: MessagesState, config: RunnableConfig | None = None
) -> ConversationMetrics:
    """
    Calculate all business metrics for a conversation.

    Aggregates metrics from:
    - Messages list (turns, message count)
    - State metadata (agent type, errors)
    - LLM responses (tokens, costs via usage_metadata)

    Args:
        state: LangGraph state with messages, agent_results, metadata
        config: Optional RunnableConfig (for future extensions)

    Returns:
        ConversationMetrics with all calculated values

    Example:
        >>> metrics = calculate_conversation_metrics(state)
        >>> print(f"Cost: ${metrics.cost_usd:.4f}, Turns: {metrics.turns}")
    """
    try:
        agent_type = extract_agent_type(state)
        messages_raw = state.get(STATE_KEY_MESSAGES, [])

        # Type guard: ensure messages is a list
        if not isinstance(messages_raw, list):
            messages_raw = []

        message_count = len(messages_raw)

        # Calculate turns (1 turn = 1 HumanMessage + 1 AIMessage pair)
        turns = calculate_conversation_turns(state)

        # Calculate total tokens and cost from messages
        tokens_total = calculate_total_tokens(messages_raw)
        cost_usd = calculate_total_cost_usd(messages_raw)

        # Infer conversation outcome
        outcome = infer_conversation_outcome(state)

        # Check for errors
        has_errors = STATE_KEY_PLANNER_ERROR in state or outcome in ("failure", "partial_success")

        logger.debug(
            "conversation_metrics_calculated",
            agent_type=agent_type,
            cost_usd=cost_usd,
            tokens_total=tokens_total,
            turns=turns,
            outcome=outcome,
            message_count=message_count,
        )

        return ConversationMetrics(
            agent_type=agent_type,
            cost_usd=cost_usd,
            tokens_total=tokens_total,
            turns=turns,
            outcome=outcome,
            message_count=message_count,
            has_errors=has_errors,
        )
    except Exception as e:
        logger.error("conversation_metrics_calculation_failed", error=str(e), exc_info=True)
        # Graceful degradation - return defaults
        return ConversationMetrics(
            agent_type="unknown",
            cost_usd=0.0,
            tokens_total=0,
            turns=0,
            outcome="failure",
            message_count=0,
            has_errors=True,
        )


async def calculate_conversation_metrics_async(
    state: MessagesState,
    config: RunnableConfig | None = None,
    db: "AsyncSession | None" = None,
) -> ConversationMetrics:
    """
    Calculate all business metrics for a conversation using DB pricing (ASYNC).

    Uses AsyncPricingService for accurate model-specific pricing from llm_model_pricing table.
    Falls back to deprecated sync version if no DB session provided.

    Args:
        state: LangGraph state with messages, agent_results, metadata
        config: Optional RunnableConfig (for future extensions)
        db: SQLAlchemy async database session (required for accurate pricing)

    Returns:
        ConversationMetrics with all calculated values
    """
    try:
        agent_type = extract_agent_type(state)
        messages_raw = state.get(STATE_KEY_MESSAGES, [])

        # Type guard: ensure messages is a list
        if not isinstance(messages_raw, list):
            messages_raw = []

        message_count = len(messages_raw)

        # Calculate turns (1 turn = 1 HumanMessage + 1 AIMessage pair)
        turns = calculate_conversation_turns(state)

        # Calculate total tokens from messages
        tokens_total = calculate_total_tokens(messages_raw)

        # Calculate cost: use async DB pricing if session provided
        if db:
            cost_usd = await calculate_total_cost_usd_async(messages_raw, db)
        else:
            # Fallback to deprecated sync version (logs warning)
            logger.warning(
                "calculate_conversation_metrics_using_deprecated_sync_pricing",
                msg="No DB session provided, using deprecated sync pricing",
            )
            cost_usd = calculate_total_cost_usd(messages_raw)

        # Infer conversation outcome
        outcome = infer_conversation_outcome(state)

        # Check for errors
        has_errors = STATE_KEY_PLANNER_ERROR in state or outcome in ("failure", "partial_success")

        logger.debug(
            "conversation_metrics_calculated_async",
            agent_type=agent_type,
            cost_usd=cost_usd,
            tokens_total=tokens_total,
            turns=turns,
            outcome=outcome,
            message_count=message_count,
            using_db_pricing=db is not None,
        )

        return ConversationMetrics(
            agent_type=agent_type,
            cost_usd=cost_usd,
            tokens_total=tokens_total,
            turns=turns,
            outcome=outcome,
            message_count=message_count,
            has_errors=has_errors,
        )
    except Exception as e:
        logger.error("conversation_metrics_async_calculation_failed", error=str(e), exc_info=True)
        # Graceful degradation - return defaults
        return ConversationMetrics(
            agent_type="unknown",
            cost_usd=0.0,
            tokens_total=0,
            turns=0,
            outcome="failure",
            message_count=0,
            has_errors=True,
        )


def extract_agent_type(state: MessagesState) -> str:
    """
    Extract agent type from state.

    Tries multiple strategies:
    1. agent_type field in state (if set by router)
    2. agent_results[0].agent_type (from executed agents)
    3. "generic" as fallback

    Args:
        state: LangGraph state

    Returns:
        Agent type string (contacts, generic, emails, etc.)
    """
    # Strategy 1: Direct agent_type field
    if "agent_type" in state:
        agent_type_value = state.get("agent_type")
        if isinstance(agent_type_value, str):
            return agent_type_value

    # Strategy 2: Extract from agent_results (dict or list of results)
    agent_results_raw = state.get(STATE_KEY_AGENT_RESULTS, {})

    # Handle dict format (current production format with composite keys)
    if agent_results_raw and isinstance(agent_results_raw, dict):
        for result in agent_results_raw.values():
            if hasattr(result, "agent_type"):
                agent_type_attr = result.agent_type
                if isinstance(agent_type_attr, str):
                    return agent_type_attr

    # Handle list format (legacy or test format)
    elif agent_results_raw and isinstance(agent_results_raw, list):
        for result in agent_results_raw:
            if hasattr(result, "agent_type"):
                agent_type_attr = result.agent_type
                if isinstance(agent_type_attr, str):
                    return agent_type_attr

    # Strategy 3: Fallback
    logger.debug("agent_type_not_found_using_fallback", fallback="generic")
    return "generic"


def calculate_total_tokens(messages: list[Any]) -> int:
    """
    Calculate total tokens consumed across all messages.

    Sums input_tokens + output_tokens from usage_metadata in AIMessages.
    This matches Langfuse token tracking methodology.

    Args:
        messages: List of LangChain messages (AIMessage, HumanMessage, etc.)

    Returns:
        Total tokens (prompt + completion) across all LLM calls
    """
    total_tokens = 0

    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue

        # Extract usage_metadata from AIMessage (LangChain >= 0.3.0)
        if hasattr(msg, "usage_metadata") and msg.usage_metadata:
            usage = msg.usage_metadata
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            total_tokens += input_tokens + output_tokens

    return total_tokens


def calculate_total_cost_usd(messages: list[Any]) -> float:
    """
    Calculate total cost in USD from token usage (SYNC - DEPRECATED).

    DEPRECATED: Use calculate_total_cost_usd_async() for accurate pricing via llm_model_pricing DB.
    This sync version uses hardcoded fallback pricing and should only be used as last resort.

    Args:
        messages: List of LangChain messages with usage_metadata

    Returns:
        Total cost in USD (float)
    """
    total_cost = 0.0

    # DEPRECATED: Simplified pricing fallback (gpt-4.1-mini rates as of 2025)
    INPUT_PRICE_PER_1M = 0.15  # USD per 1M input tokens
    OUTPUT_PRICE_PER_1M = 0.60  # USD per 1M output tokens

    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue

        if hasattr(msg, "usage_metadata") and msg.usage_metadata:
            usage = msg.usage_metadata
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            # Calculate cost using fallback pricing
            input_cost = (input_tokens / 1_000_000) * INPUT_PRICE_PER_1M
            output_cost = (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M
            total_cost += input_cost + output_cost

    return round(total_cost, 6)  # Round to 6 decimals ($0.000001 precision)


async def calculate_total_cost_usd_async(
    messages: list[Any],
    db: "AsyncSession",
) -> float:
    """
    Calculate total cost in USD from token usage using DB pricing (ASYNC).

    Uses AsyncPricingService to get model-specific pricing from llm_model_pricing table.
    Supports INPUT, OUTPUT, and CACHE token types with differentiated pricing.

    Args:
        messages: List of LangChain messages with usage_metadata
        db: SQLAlchemy async database session

    Returns:
        Total cost in USD (float)

    Token Types Handled:
        - input_tokens: Standard input tokens (full price)
        - output_tokens: Output/completion tokens
        - cached_tokens: From input_token_details.cache_read (reduced price)
    """
    from src.domains.llm.pricing_service import AsyncPricingService

    total_cost = 0.0
    pricing_service = AsyncPricingService(db)

    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue

        if hasattr(msg, "usage_metadata") and msg.usage_metadata:
            usage = msg.usage_metadata
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            # Extract cached_tokens from input_token_details (OpenAI pattern)
            # LangChain v1.0+ returns: {"input_token_details": {"cache_read": N}}
            cached_tokens = 0
            if "input_token_details" in usage:
                cached_tokens = usage["input_token_details"].get("cache_read", 0)
            # Anthropic pattern: cache_creation_input_tokens, cache_read_input_tokens
            elif "cache_read_input_tokens" in usage:
                cached_tokens = int(usage.get("cache_read_input_tokens", 0))  # type: ignore[call-overload]

            # Extract model name from message metadata
            model = None
            if hasattr(msg, "response_metadata") and msg.response_metadata:
                model = msg.response_metadata.get("model_name") or msg.response_metadata.get(
                    "model"
                )
            if not model and hasattr(msg, "additional_kwargs"):
                model = msg.additional_kwargs.get("model")

            if not model:
                model = "gpt-4.1-mini"  # Default fallback

            # Calculate cost using AsyncPricingService (DB pricing)
            cost_usd, _ = await pricing_service.calculate_token_cost(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
            )
            total_cost += cost_usd

    return round(total_cost, 6)


def calculate_conversation_turns(state: MessagesState) -> int:
    """
    Calculate number of user-agent turns in conversation.

    A turn is defined as:
    - 1 HumanMessage (user input) followed by
    - 1 AIMessage (agent response)

    Consecutive HumanMessages count as 1 turn (user clarification).
    Consecutive AIMessages count as 1 turn (agent thinking/planning).

    Args:
        state: LangGraph state with messages list

    Returns:
        Number of complete user-agent turns

    Example:
        >>> messages = [HumanMessage("Hi"), AIMessage("Hello"), HumanMessage("Help"), AIMessage("Sure")]
        >>> turns = calculate_conversation_turns({"messages": messages})
        >>> assert turns == 2
    """
    messages_raw = state.get(STATE_KEY_MESSAGES, [])

    # Type guard: ensure messages is a list
    if not isinstance(messages_raw, list) or not messages_raw:
        return 0

    turns = 0
    last_was_human = False

    for msg in messages_raw:
        if isinstance(msg, HumanMessage):
            last_was_human = True
        elif isinstance(msg, AIMessage):
            if last_was_human:
                turns += 1
                last_was_human = False

    return turns


def infer_conversation_outcome(state: MessagesState) -> str:
    """
    Infer conversation outcome from state using heuristics.

    Outcome classification:
    - "success": Conversation completed without errors, agent_results present
    - "failure": Critical error (planner_error, no agent_results)
    - "partial_success": Some agent_results present but with errors/warnings
    - "abandoned": No clear completion (no agent_results, no errors)

    Heuristics:
    1. planner_error in state → "failure"
    2. agent_results present with all success → "success"
    3. agent_results present with some failures → "partial_success"
    4. No agent_results, no errors → "abandoned"

    Args:
        state: LangGraph state with agent_results, planner_error, metadata

    Returns:
        Outcome string: "success", "failure", "partial_success", or "abandoned"

    Note:
        This is a heuristic-based classification. For production, consider:
        - Explicit outcome field set by response_node
        - User feedback integration
        - Tool execution success tracking
    """
    # Check for critical errors
    if STATE_KEY_PLANNER_ERROR in state:
        return "failure"

    # Check agent_results
    agent_results_raw = state.get(STATE_KEY_AGENT_RESULTS, [])

    if not agent_results_raw:
        # No results: user abandoned or conversation incomplete
        messages_raw = state.get(STATE_KEY_MESSAGES, [])

        # Type guard for messages
        if isinstance(messages_raw, list) and len(messages_raw) <= 2:
            # Very short conversation, likely abandoned
            return "abandoned"
        return "failure"  # Longer conversation without results = failure

    # Analyze agent_results for success/failure
    has_success = False
    has_failure = False

    # Type guard: ensure agent_results is iterable
    # agent_results can be dict (keyed by agent name) or list
    results_iterable = []
    if isinstance(agent_results_raw, dict):
        results_iterable = list(agent_results_raw.values())
    elif isinstance(agent_results_raw, list):
        results_iterable = agent_results_raw

    for result in results_iterable:
        # Check if result has status/success indicators
        if hasattr(result, "status"):
            status = result.status
            if status == "success":
                has_success = True
            elif status in ("failure", "error"):
                has_failure = True
        elif hasattr(result, "data"):
            # If result has data, consider it success
            has_success = True

    # Classify outcome
    if has_success and not has_failure:
        return "success"
    elif has_success and has_failure:
        return "partial_success"
    elif has_failure:
        return "failure"
    else:
        # Results present but no clear success/failure indicators
        return "success"  # Assume success if results exist


# ============================================================================
# TOKEN EFFICIENCY CALCULATION
# ============================================================================


def calculate_token_efficiency_ratio(input_tokens: int, output_tokens: int) -> float:
    """
    Calculate token efficiency ratio (output/input).

    High ratio (> 3.0) indicates verbose agent (potential prompt inefficiency).
    Low ratio (< 0.5) indicates concise agent.

    Args:
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens

    Returns:
        Ratio (float), or 0.0 if input_tokens is 0

    Example:
        >>> ratio = calculate_token_efficiency_ratio(100, 250)
        >>> assert ratio == 2.5  # Agent generated 2.5x more tokens than input
    """
    if input_tokens == 0:
        return 0.0
    return round(output_tokens / input_tokens, 2)


# ============================================================================
# HITL METRICS CALCULATION
# ============================================================================


def calculate_agent_tool_approval_rate(state: MessagesState) -> float:
    """
    Calculate HITL tool approval rate for conversation.

    Approval rate = approved_tools / total_tools_proposed (0.0-1.0).

    Low approval rate (<0.5) indicates:
    - Poor agent behavior (wrong tools proposed)
    - Overly conservative users
    - Misaligned expectations

    Args:
        state: LangGraph state with HITL metadata

    Returns:
        Approval rate (0.0-1.0), or 0.0 if no tools proposed

    Note:
        Phase 3.2 MVP: Simplified calculation from state metadata.
        Production: Track approvals in dedicated HITL events.
    """
    # TODO (Phase 3.2.2): Implement approval tracking in approval_gate_node
    # For now, return 0.0 as placeholder (will be implemented in Step 2.3)
    return 0.0


# ============================================================================
# AGENT ROUTING ACCURACY (ADVANCED - PHASE 3.2 P2)
# ============================================================================


def calculate_agent_routing_accuracy(state: MessagesState) -> float:
    """
    Calculate router accuracy (0.0-1.0).

    Requires manual labeling or HITL feedback to determine "correct" routing.
    This is a complex metric requiring production data analysis.

    Args:
        state: LangGraph state with routing_history

    Returns:
        Accuracy (0.0-1.0), or 0.0 if not calculable

    Note:
        Phase 3.2 P2 (deferred): Requires:
        - User feedback collection ("was this the right agent?")
        - Ground truth labeling dataset
        - Statistical confidence calculation

        For MVP, this returns 0.0 placeholder.
    """
    # TODO (Phase 3.2 P2): Implement routing accuracy tracking
    # Requires user feedback integration and ground truth dataset
    return 0.0
