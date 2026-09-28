"""
Business Metrics Calculation Service (Phase 3.2).

Calculates conversation-level business metrics for Prometheus tracking.
Separates calculation logic (complex) from instrumentation (simple).

Metrics calculated:
- Conversation cost (USD) from LLM token usage
- Total tokens consumed (prompt + completion)
- Conversation turns (user-agent exchanges)
- Turn outcome (success/partial_success/failure/no_agent), from the turn's
  own evidence
- Agent type extraction (the turn's execution mode)

Architecture:
- Calculation functions with no counter, no database and no network: a
  message is priced by the in-memory pricing cache (the tariffs the
  platform's own ledger prices with) through its quiet door, which counts
  no fallback: the doors that priced the call counted its miss when it was
  made
- One read of the database, the run's ledger (``current_turn_cost_usd``), on a
  session of its own
- Graceful degradation (returns defaults on errors)

The outcome is read from the turn's own evidence (``infer_conversation_outcome``);
a calculation that fails judges no agent. Structured logging throughout.

Phase: 3.2 - Business Metrics
Date: 2025-11-23
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from src.core.constants import NODE_INITIATIVE
from src.core.context import current_tracker
from src.core.field_names import (
    FIELD_COST_EUR,
    FIELD_FAILED_STEPS,
    FIELD_REACT_SYNTHESIS,
    FIELD_STATUS,
)
from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_MESSAGES,
    STATE_KEY_PLANNING_RESULT,
    AgentResultStatus,
    make_agent_result_key,
)
from src.domains.agents.drafts.models import DraftAction
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.react_recovery import declared_unresolved
from src.domains.agents.utils.message_filters import current_turn_responses, tool_call_ran
from src.domains.chat.repository import ChatRepository
from src.domains.diagnostics.failure_context import tool_message_failed
from src.infrastructure.cache.pricing_cache import (
    get_cached_usd_eur_rate,
    quote_cached_cost_usd,
)
from src.infrastructure.database import get_db_context
from src.infrastructure.llm.usage_metadata import (
    model_name_of_response,
    tokens_from_usage_metadata,
)

logger = structlog.get_logger(__name__)

#: The outcomes of a turn, as the ``outcome`` label of
#: ``agent_success_rate_total`` reads them.
OUTCOME_SUCCESS = "success"
OUTCOME_PARTIAL_SUCCESS = "partial_success"
OUTCOME_FAILURE = "failure"
#: The turn left no agent execution to read — a conversational answer, or a
#: skill the response node ran itself, whose runner result stays in that node
#: (``skill_runner_outcomes_total`` counts it). Not counted on any
#: ``agent_success_rate_total`` series.
OUTCOME_NO_AGENT = "no_agent"

#: One executed draft's status, as ``DraftExecutionResult.to_agent_result``
#: writes it, as a verdict. A batch's aggregate status is not read: it says
#: ``partial_error`` for a batch whose every entry failed.
_DRAFT_ENTRY_VERDICTS: dict[str, bool] = {"success": True, "error": False}


# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass(frozen=True)
class ConversationMetrics:
    """
    Business metrics of one turn, as the response node records them.

    Attributes:
        agent_type: The turn's execution mode (pipeline, react), or generic
        cost_usd: Total conversation cost in USD
        tokens_total: Total tokens (prompt + completion)
        turns: Number of user-agent turns
        outcome: The turn's outcome (success, failure, partial_success, no_agent)
        message_count: Total messages in conversation
    """

    agent_type: str
    cost_usd: float
    tokens_total: int
    turns: int
    outcome: str  # success, failure, partial_success, no_agent
    message_count: int


# ============================================================================
# METRICS CALCULATION FUNCTIONS
# ============================================================================


def calculate_conversation_metrics(
    state: MessagesState,
    config: RunnableConfig | None = None,
    draft_result: Mapping[str, Any] | None = None,
) -> ConversationMetrics:
    """
    Calculate all business metrics for a conversation.

    Aggregates metrics from:
    - Messages list (turns, message count)
    - State metadata (agent type, the turn's evidence)
    - LLM responses (tokens and cost, from each message's usage metadata,
      priced by the pricing cache)

    No database, no network, no counter — a metric computed while the
    person's turn ends must never hold a transaction open across a wait
    (ADR-304).

    Args:
        state: LangGraph state with messages, agent_results, metadata
        config: Optional RunnableConfig (for future extensions)
        draft_result: The execution of the draft the person decided, when the
            turn ran one

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

        outcome = infer_conversation_outcome(state, draft_result)
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
        )
    except Exception as e:
        # By its type: the state it read carries the person's words (ADR-317).
        logger.error(
            "conversation_metrics_calculation_failed", error_type=type(e).__name__, exc_info=True
        )
        # Graceful degradation: a metrics failure judges no agent.
        return ConversationMetrics(
            agent_type="unknown",
            cost_usd=0.0,
            tokens_total=0,
            turns=0,
            outcome=OUTCOME_NO_AGENT,
            message_count=0,
        )


def extract_agent_type(state: MessagesState) -> str:
    """
    The agent label of a turn: its execution mode (``pipeline``, ``react``).

    The results the graph writes are dicts that name no domain, and the
    state declares no ``agent_type`` key (LangGraph drops what it does not
    declare): read there, every turn was « generic ».

    Args:
        state: LangGraph state

    Returns:
        The execution mode, or ``generic`` when the state carries none.
    """
    execution_mode = state.get("execution_mode")
    if isinstance(execution_mode, str) and execution_mode:
        return execution_mode
    logger.debug("agent_type_not_found_using_fallback", fallback="generic")
    return "generic"


def calculate_total_tokens(messages: list[Any]) -> int:
    """
    Calculate total tokens consumed across all messages.

    Sums every AIMessage's prompt (cache reads included) and completion
    tokens, read through the one usage reader (``tokens_from_usage_metadata``).
    This matches Langfuse token tracking methodology.

    Args:
        messages: List of LangChain messages (AIMessage, HumanMessage, etc.)

    Returns:
        Total tokens (prompt + completion) across all LLM calls
    """
    total_tokens = 0
    for msg in messages:
        if isinstance(msg, AIMessage):
            usage = tokens_from_usage_metadata(msg.usage_metadata)
            total_tokens += usage.prompt + usage.cached + usage.completion
    return total_tokens


def calculate_total_cost_usd(messages: list[Any]) -> float:
    """
    Calculate total cost in USD of the model calls the messages carry.

    Each AIMessage is priced by the in-memory pricing cache — the tariffs the
    platform's own ledger prices with, cache reads and writes apart (ADR-306)
    — at the model the response names. A response that names no model is not
    priced: another model's tariff would be a figure nobody paid. A model the
    cache cannot price adds nothing and counts no miss here: this runs over
    the thread's window at every turn, and the doors that priced the call
    counted its miss when it was made.

    Args:
        messages: List of LangChain messages with usage_metadata

    Returns:
        Total cost in USD, rounded to six decimals.
    """
    total_cost = 0.0
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        usage = tokens_from_usage_metadata(msg.usage_metadata)
        model = model_name_of_response(msg)
        if usage.is_empty or model is None:
            continue
        cost_usd = quote_cached_cost_usd(
            model=model,
            prompt_tokens=usage.prompt,
            completion_tokens=usage.completion,
            cached_tokens=usage.cached,
            cache_write_tokens=usage.cache_write,
        )
        total_cost += cost_usd or 0.0
    return round(total_cost, 6)  # Round to 6 decimals ($0.000001 precision)


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


def _status_and_partial(result: Any) -> tuple[str | None, bool]:
    """Status and « carries failed steps » of one agent result.

    Reads a DICT first — the real shape, since ``agent_results`` holds
    ``AgentResult.model_dump()`` output. Asking ``hasattr(result, "status")``
    on a dict is always False, so a pipeline turn (failed ones included) fell
    through to « results exist, assume success » — a verdict nobody read, since
    the presence of ``planner_error`` classified every turn a failure before it
    (ADR-303, ADR-323).

    Args:
        result: One entry of ``agent_results``, dict or object.

    Returns:
        ``(status, carries_failed_steps)``; status is None when absent.
    """
    if isinstance(result, dict):
        return result.get(FIELD_STATUS), bool(result.get(FIELD_FAILED_STEPS))
    return getattr(result, "status", None), bool(getattr(result, "failed_steps", None))


def _payload(result: Any) -> Any:
    return result.get("data") if isinstance(result, dict) else getattr(result, "data", None)


def _has_data(result: Any) -> bool:
    """Whether a status-less payload carries data (so it did run)."""
    return _payload(result) is not None


def _is_react_synthesis(result: Any) -> bool:
    """The ReAct loop's ANSWER, merged by the response node — not an execution."""
    payload = _payload(result)
    return isinstance(payload, dict) and FIELD_REACT_SYNTHESIS in payload


def _current_turn_results(state: MessagesState) -> list[Any]:
    """The agent results of THIS turn, the initiative's own reads left out.

    ``agent_results`` is not reset per turn: it keeps every turn's entries under
    ``"<turn_id>:<agent>"`` keys, and the cleanup reads a key with no turn as
    the OLDEST turn's. Read whole, a later turn was judged on an earlier turn's
    agents — a stale bare error key made every later chat turn a failure. A
    state with no turn id has nothing to anchor on: read whole.
    What the initiative looked up of its own accord (ADR-062) is not what the
    person asked for: a lookup of its failing never failed their request.
    """
    raw = state.get(STATE_KEY_AGENT_RESULTS) or {}
    if not isinstance(raw, dict):
        return []
    current = state.get(STATE_KEY_CURRENT_TURN_ID)
    if not isinstance(current, int):
        return list(raw.values())
    prefix, initiative = f"{current}:", make_agent_result_key(current, NODE_INITIATIVE)
    return [
        value for key, value in raw.items() if str(key).startswith(prefix) and key != initiative
    ]


def _result_verdicts(results: list[Any]) -> list[bool]:
    """One verdict per outcome the turn's agent results state.

    A partial plan is a SUCCESS that still failed somewhere: the field says so,
    the status cannot (ADR-303). The ReAct synthesis is the loop's answer, and
    its tools speak for it; a legacy payload with no status but data ran.
    """
    verdicts: list[bool] = []
    for result in results:
        status, carries_failed_steps = _status_and_partial(result)
        if status == AgentResultStatus.SUCCESS.value:
            verdicts.append(True)
            if carries_failed_steps:
                verdicts.append(False)
        elif status == AgentResultStatus.ERROR.value:
            verdicts.append(False)
        elif status is None and _has_data(result) and not _is_react_synthesis(result):
            verdicts.append(True)
    return verdicts


def _tool_verdicts(state: MessagesState) -> list[bool]:
    """The ReAct loop's evidence, judged on its RESULT (ADR-310).

    Its tool calls of THIS turn are read among the messages after the person's,
    counted from the end (the reducer trims the head — and, in a very long
    turn, the turn's first results with it), through the predicate the honesty
    directive reads. A call the loop never ran — declined by the person, a
    repeat the loop guard blocked — is no verdict. A failure the loop got past
    (its own call corrected, another source) fails nothing: what did not end
    complete is what the answer declares unresolved, a loop its budget cut, or
    calls that all failed. The pipeline writes no ``ToolMessage``: its agents'
    results speak for it.
    """
    messages = state.get(STATE_KEY_MESSAGES)
    turn = current_turn_responses(messages) if isinstance(messages, list) else []
    ran = [
        not tool_message_failed(m) for m in turn if isinstance(m, ToolMessage) and tool_call_ran(m)
    ]
    verdicts = [True] if any(ran) else []
    if _react_incomplete(state) or (ran and not any(ran)):
        verdicts.append(False)
    return verdicts


def _react_incomplete(state: MessagesState) -> bool:
    """Whether the loop's answer did not end complete: cut, or a gap declared."""
    react_result = state.get("react_agent_result")
    if not isinstance(react_result, dict):
        return False
    if isinstance(react_result.get("truncation"), dict):
        return True
    final = react_result.get("final_message")
    return bool(declared_unresolved(AIMessage(content=final))) if isinstance(final, str) else False


def _executed_drafts(draft_result: Mapping[str, Any]) -> list[Any]:
    """The drafts a decision executed: a batch's entries, the confirmed draft, or none.

    A cancellation executed nothing, nor did an edit (it asks again).
    """
    action = draft_result.get("action")
    if action == DraftAction.CONFIRM_BATCH.value:
        data = draft_result.get("data")
        return list(data.get("batch_results") or []) if isinstance(data, Mapping) else []
    return [draft_result] if action == DraftAction.CONFIRM.value else []


def _draft_verdicts(draft_result: Mapping[str, Any] | None) -> list[bool]:
    """The acts the person confirmed, one verdict per draft executed.

    An entry of a batch the person cancelled executed nothing: no verdict.
    """
    entries = _executed_drafts(draft_result) if draft_result else []
    statuses = [entry.get(FIELD_STATUS) for entry in entries if isinstance(entry, Mapping)]
    return [_DRAFT_ENTRY_VERDICTS[status] for status in statuses if status in _DRAFT_ENTRY_VERDICTS]


def _planning_failed(state: MessagesState) -> bool:
    """The planner produced no plan THIS turn (the router resets its verdict).

    Its failure sends the turn to the response with no agent result: read on
    the results alone, it passed for a conversational turn and was never
    counted.
    """
    result = state.get(STATE_KEY_PLANNING_RESULT)
    success = (
        result.get("success") if isinstance(result, dict) else getattr(result, "success", None)
    )
    return success is False


def infer_conversation_outcome(
    state: MessagesState, draft_result: Mapping[str, Any] | None = None
) -> str:
    """The outcome of the CURRENT turn, from its own evidence.

    Each read for THIS turn only: the planner's verdict, the agents' results,
    the ReAct loop's result, and the execution of the draft the person
    decided — the act they approved.

    Args:
        state: LangGraph state.
        draft_result: The execution of the draft the person decided, when the
            response node ran one — it is in no state key.

    Returns:
        ``OUTCOME_FAILURE`` when the planner produced no plan or every verdict
        failed, ``OUTCOME_SUCCESS`` when every verdict succeeded,
        ``OUTCOME_PARTIAL_SUCCESS`` when both, and ``OUTCOME_NO_AGENT`` when the
        turn left no execution to read (see ``OUTCOME_NO_AGENT``).
    """
    if _planning_failed(state):
        return OUTCOME_FAILURE
    verdicts = [
        *_result_verdicts(_current_turn_results(state)),
        *_tool_verdicts(state),
        *_draft_verdicts(draft_result),
    ]
    if not verdicts:
        return OUTCOME_NO_AGENT
    if all(verdicts):
        return OUTCOME_SUCCESS
    return OUTCOME_PARTIAL_SUCCESS if any(verdicts) else OUTCOME_FAILURE


async def current_turn_cost_usd() -> float | None:
    """What the model calls of THIS run cost when it answered, in USD.

    The thread's messages cannot say it: they carry the ReAct loop's calls and
    the earlier turns' answers, never the router's, the planner's or the
    agents'. A turn resumed after a question keeps its run id, and the half
    before the question was filed when it stopped: the cost is what the run's
    ledger row holds (``total_cost_eur``, the model's — Maps, images and speech
    are billed apart) plus what the running tracker has not filed yet. The
    calls made after the answer (the memory, journal and interest extractions)
    are filed later under the same run and are not in it. Priced in euros,
    converted back at the cached exchange rate.

    Read on a session of its own — the one database read of this module — and
    after the turn's other samples: a ledger that cannot be read costs this one
    figure, never the turn's other metrics.

    Returns:
        The cost, or None outside a tracked run or when the ledger cannot be
        read — whatever the database or its driver raised, opening the
        connection (asyncpg refuses one with classes of its own, neither
        ``SQLAlchemyError`` nor ``OSError``), running the query, or committing
        at the session's exit. An unknown cost is observed as none; a
        cancellation is not an ``Exception`` and passes.
    """
    tracker = current_tracker.get()
    rate = get_cached_usd_eur_rate()
    if tracker is None or rate <= 0:
        return None
    try:
        async with get_db_context() as db:
            filed = await ChatRepository(db).get_token_summary_by_run_id(tracker.run_id)
            eur = float(filed.total_cost_eur) if filed is not None else 0.0
    except Exception as exc:  # noqa: BLE001 - a metric's read never fails its turn
        logger.warning("turn_cost_ledger_unreadable", error_type=type(exc).__name__)
        return None
    return round((eur + float(tracker.get_summary()[FIELD_COST_EUR])) / rate, 6)


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
