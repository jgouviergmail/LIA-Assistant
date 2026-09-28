"""
Tests for business metrics calculation service (Phase 3.2).

Tests all calculation functions with comprehensive coverage:
- Conversation metrics aggregation
- Token and cost calculation
- Conversation turns parsing
- Outcome inference heuristics
- Agent type extraction
- Token efficiency ratio

Coverage target: 80%+

Phase: 3.2 - Business Metrics
Date: 2025-11-23
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.ai import InputTokenDetails, UsageMetadata
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.core.context import current_tracker
from src.domains.agents.models import MessagesState, create_initial_state
from src.domains.agents.services.business_metrics import (
    OUTCOME_NO_AGENT,
    ConversationMetrics,
    calculate_conversation_metrics,
    calculate_conversation_turns,
    calculate_token_efficiency_ratio,
    calculate_total_cost_usd,
    calculate_total_tokens,
    current_turn_cost_usd,
    extract_agent_type,
    infer_conversation_outcome,
)
from src.domains.agents.services.draft_executor import DraftExecutionResult
from src.domains.agents.services.planner.planning_result import PlanningResult
from src.domains.agents.utils.loop_guard import repeated_call_message
from src.domains.agents.utils.message_filters import tool_call_not_run
from src.infrastructure.cache import pricing_cache
from src.infrastructure.cache.pricing_cache import CachedModelPrice, PricingCacheData
from tests.helpers.pricing import fallbacks_counted

_BM = "src.domains.agents.services.business_metrics"


def _state(*messages: BaseMessage) -> MessagesState:
    """A state as the graph builds it, its thread holding ``messages``."""
    state = create_initial_state(uuid4(), session_id="s", run_id="r")
    state["messages"] = list(messages)
    return state


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_messages_with_tokens() -> list[BaseMessage]:
    """Sample messages with usage_metadata (LangChain >= 0.3.0 format)."""
    return [
        HumanMessage(content="Hello"),
        AIMessage(
            content="Hi there!",
            usage_metadata={
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            },
        ),
        HumanMessage(content="How are you?"),
        AIMessage(
            content="I'm doing well!",
            usage_metadata={
                "input_tokens": 200,
                "output_tokens": 75,
                "total_tokens": 275,
            },
        ),
    ]


@pytest.fixture
def sample_state_success() -> MessagesState:
    """A pipeline turn whose agent answered, its answer priced."""
    state = _state(
        HumanMessage(content="Search contacts"),
        AIMessage(
            content="Found 5 contacts",
            usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            response_metadata={"model_name": "priced-model"},
        ),
    )
    state["execution_mode"] = "pipeline"
    state["current_turn_id"] = 1
    state["agent_results"] = {"1:contacts_agent": {"status": "success", "data": {"contacts": []}}}
    return state


@pytest.fixture
def sample_state_failure() -> MessagesState:
    """A turn whose planner produced no plan — what the planner writes."""
    state = _state(HumanMessage(content="Search contacts"))
    state["execution_mode"] = "pipeline"
    state["planning_result"] = PlanningResult(plan=None, success=False, error="no plan")
    return state


# ============================================================================
# TESTS - calculate_conversation_metrics()
# ============================================================================


def test_calculate_conversation_metrics_success(sample_state_success: MessagesState) -> None:
    """Test conversation metrics calculation for successful conversation."""
    with patch(f"{_BM}.quote_cached_cost_usd", return_value=0.01):
        metrics = calculate_conversation_metrics(sample_state_success, config=None)

    assert isinstance(metrics, ConversationMetrics)
    assert metrics.agent_type == "pipeline"
    assert metrics.tokens_total == 150  # 100 + 50
    assert metrics.turns == 1  # 1 HumanMessage + 1 AIMessage
    assert metrics.outcome == "success"
    assert metrics.message_count == 2
    assert metrics.cost_usd == 0.01  # the platform's tariff for that model


def test_calculate_conversation_metrics_failure(sample_state_failure: MessagesState) -> None:
    """Test conversation metrics calculation for failed conversation."""
    metrics = calculate_conversation_metrics(sample_state_failure, config=None)

    assert metrics.agent_type == "pipeline"
    assert metrics.outcome == "failure"  # the planner produced no plan
    assert metrics.message_count == 1


def test_a_conversational_turn_is_no_agent_execution() -> None:
    """A turn that ran no agent is neither abandoned nor failed: it ran none."""
    state = _state(HumanMessage(content="Hi"), AIMessage(content="Hello"))

    metrics = calculate_conversation_metrics(state, config=None)

    assert metrics.outcome == OUTCOME_NO_AGENT


# ============================================================================
# TESTS - calculate_total_tokens()
# ============================================================================


def test_calculate_total_tokens_with_usage_metadata(
    sample_messages_with_tokens: list[BaseMessage],
) -> None:
    """Test token calculation with usage_metadata."""
    total = calculate_total_tokens(sample_messages_with_tokens)

    # 100 + 50 (first AIMessage) + 200 + 75 (second AIMessage) = 425
    assert total == 425


def test_calculate_total_tokens_empty_messages() -> None:
    """Test token calculation with empty messages list."""
    total = calculate_total_tokens([])

    assert total == 0


def test_calculate_total_tokens_no_ai_messages() -> None:
    """Test token calculation with no AIMessages."""
    messages = [
        HumanMessage(content="Hello"),
        SystemMessage(content="System prompt"),
    ]

    total = calculate_total_tokens(messages)

    assert total == 0  # No AIMessages with usage_metadata


def test_calculate_total_tokens_missing_usage_metadata() -> None:
    """Test token calculation when AIMessage lacks usage_metadata."""
    messages = [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi"),  # No usage_metadata
    ]

    total = calculate_total_tokens(messages)

    assert total == 0  # Gracefully handles missing usage_metadata


# ============================================================================
# TESTS - calculate_total_cost_usd()
# ============================================================================


def _priced(usage: UsageMetadata, model: str = "model-a") -> AIMessage:
    """An answer of ``model`` whose provider reported ``usage``."""
    return AIMessage(
        content="answer", usage_metadata=usage, response_metadata={"model_name": model}
    )


def _tariff(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int,
    cache_write_tokens: int,
) -> float:
    """One USD per million prompt tokens, two per million completion tokens."""
    return (prompt_tokens + 2 * completion_tokens) / 1_000_000


def test_each_answer_is_priced_by_the_platform_s_tariff_of_its_own_model() -> None:
    """One hardcoded tariff priced every model: a figure nobody paid."""
    answers = [
        _priced(UsageMetadata(input_tokens=100, output_tokens=50, total_tokens=150)),
        _priced(UsageMetadata(input_tokens=200, output_tokens=75, total_tokens=275), "model-b"),
    ]
    tariffs = {"model-a": 0.25, "model-b": 0.5}

    with patch(
        f"{_BM}.quote_cached_cost_usd",
        side_effect=lambda **call: tariffs[call["model"]],
    ) as priced:
        cost = calculate_total_cost_usd(answers)

    assert cost == 0.75
    assert [call.kwargs["model"] for call in priced.call_args_list] == ["model-a", "model-b"]


def test_cache_reads_and_writes_are_priced_apart() -> None:
    """Read through the one usage reader: the prompt excludes the cache reads,
    and the writes owe their own surcharge (ADR-306)."""
    answer = _priced(
        UsageMetadata(
            input_tokens=1000,
            output_tokens=40,
            total_tokens=1040,
            input_token_details=InputTokenDetails(cache_read=600, cache_creation=100),
        )
    )

    with patch(f"{_BM}.quote_cached_cost_usd", return_value=0.0) as priced:
        calculate_total_cost_usd([answer])

    assert priced.call_args.kwargs == {
        "model": "model-a",
        "prompt_tokens": 400,
        "completion_tokens": 40,
        "cached_tokens": 600,
        "cache_write_tokens": 100,
    }


def test_an_answer_naming_no_model_is_never_priced_at_another_s_tariff() -> None:
    unnamed = AIMessage(
        content="answer",
        usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    )

    with patch(f"{_BM}.quote_cached_cost_usd", return_value=9.0) as priced:
        cost = calculate_total_cost_usd([unnamed])

    assert cost == 0.0
    priced.assert_not_called()


def test_calculate_total_cost_usd_zero_tokens() -> None:
    """Test cost calculation with zero tokens."""
    messages = [HumanMessage(content="Hello")]

    cost = calculate_total_cost_usd(messages)

    assert cost == 0.0


def test_calculate_total_cost_usd_precision() -> None:
    """The total is rounded to six decimals."""
    answer = _priced(UsageMetadata(input_tokens=1, output_tokens=1, total_tokens=2))

    with patch(f"{_BM}.quote_cached_cost_usd", return_value=0.00000075):
        cost = calculate_total_cost_usd([answer])

    assert cost == 0.000001


def test_an_answer_is_priced_at_the_cached_tariff_of_its_model() -> None:
    """Through the real cache: the platform's tariff for the model named."""
    cache = PricingCacheData(
        models={
            "model-a": CachedModelPrice(
                input_unit_price=1.0, output_unit_price=2.0, cached_input_unit_price=0.5
            )
        },
        usd_eur_rate=1.0,
        last_refresh_ts=0.0,
    )
    answer = _priced(
        UsageMetadata(input_tokens=1_000_000, output_tokens=500_000, total_tokens=1_500_000)
    )

    with patch.object(pricing_cache, "_local_cache", cache):
        assert calculate_total_cost_usd([answer]) == 2.0


@pytest.mark.parametrize(
    "cache",
    [None, PricingCacheData(models={}, usd_eur_rate=1.0, last_refresh_ts=0.0)],
    ids=["cold_cache", "unpriced_model"],
)
def test_a_price_the_cache_cannot_give_adds_nothing_and_counts_no_miss(
    cache: PricingCacheData | None,
) -> None:
    """The miss was counted when the call was priced. This prices the thread's
    window again at every turn: counting it here would count every unpriced
    answer of the window again at every turn."""
    thread = [_priced(UsageMetadata(input_tokens=10, output_tokens=5, total_tokens=15))] * 3
    before = fallbacks_counted()

    with patch.object(pricing_cache, "_local_cache", cache):
        cost = calculate_total_cost_usd(thread)

    assert cost == 0.0
    assert fallbacks_counted() == before


def test_the_token_total_counts_the_cache_reads() -> None:
    """The one reader's prompt EXCLUDES the cache reads: the total adds them
    back, or every cached prompt would shrink the figure."""
    answer = _priced(
        UsageMetadata(
            input_tokens=1000,
            output_tokens=40,
            total_tokens=1040,
            input_token_details=InputTokenDetails(cache_read=600, cache_creation=100),
        )
    )

    assert calculate_total_tokens([answer]) == 1040


# ============================================================================
# TESTS - calculate_conversation_turns()
# ============================================================================


def test_calculate_conversation_turns_simple() -> None:
    """Test turn calculation with simple alternating messages."""
    state = _state(
        HumanMessage(content="Hi"),
        AIMessage(content="Hello"),
        HumanMessage(content="How are you?"),
        AIMessage(content="Good"),
    )

    turns = calculate_conversation_turns(state)

    assert turns == 2  # 2 Human-AI pairs


def test_calculate_conversation_turns_consecutive_messages() -> None:
    """Test turn calculation with consecutive HumanMessages."""
    state = _state(
        HumanMessage(content="Hi"),
        HumanMessage(content="Are you there?"),  # Consecutive
        AIMessage(content="Yes, hello!"),
    )

    turns = calculate_conversation_turns(state)

    assert turns == 1  # Consecutive HumanMessages = 1 turn


def test_calculate_conversation_turns_empty() -> None:
    """Test turn calculation with empty messages."""
    state = _state()

    turns = calculate_conversation_turns(state)

    assert turns == 0


def test_calculate_conversation_turns_only_human() -> None:
    """Test turn calculation with only HumanMessages."""
    state = _state(HumanMessage(content="Hi"), HumanMessage(content="Hello?"))

    turns = calculate_conversation_turns(state)

    assert turns == 0  # No AIMessage, no complete turn


def test_calculate_conversation_turns_system_messages() -> None:
    """Test turn calculation ignores SystemMessages."""
    state = _state(
        SystemMessage(content="You are a helpful assistant"),
        HumanMessage(content="Hi"),
        AIMessage(content="Hello"),
    )

    turns = calculate_conversation_turns(state)

    assert turns == 1  # SystemMessage ignored


# ============================================================================
# TESTS - infer_conversation_outcome()
# ============================================================================


def test_infer_conversation_outcome_success() -> None:
    """Test outcome inference for successful conversation."""
    state = _state(HumanMessage(content="Search"), AIMessage(content="Found"))
    state["current_turn_id"] = 1
    state["agent_results"] = {"1:contacts_agent": {"status": "success", "data": {}}}

    outcome = infer_conversation_outcome(state)

    assert outcome == "success"


def test_a_planner_error_key_nobody_writes_judges_nothing() -> None:
    """``planner_error`` has no writer: a test that set it froze a fictional
    shape. The planner's verdict is its ``planning_result``."""
    state = _state(HumanMessage(content="Search"))
    state["planner_error"] = {"message": "Validation failed"}

    assert infer_conversation_outcome(state) == OUTCOME_NO_AGENT


def test_a_long_thread_s_conversational_turn_is_no_failure() -> None:
    """Judged on the thread, every turn after the first exchange read « failure »."""
    state = _state(
        HumanMessage(content="Search"),
        AIMessage(content="Searching..."),
        HumanMessage(content="Thanks"),
    )

    assert infer_conversation_outcome(state) == OUTCOME_NO_AGENT


def test_a_first_conversational_turn_is_no_agent_execution() -> None:
    state = _state(HumanMessage(content="Hi"))

    assert infer_conversation_outcome(state) == OUTCOME_NO_AGENT


def test_infer_conversation_outcome_partial_success() -> None:
    """A plan that produced AND failed is a partial success (ADR-303).

    The fixture is the REAL shape — ``agent_results`` holds the output of
    ``AgentResult.model_dump()``, a dict. It used to build attribute-only
    objects carrying ``status="failure"``, a value no producer writes: on real
    dicts ``hasattr(result, "status")`` is always False, so every pipeline
    turn, failed ones included, was counted a success.
    """
    state = _state(HumanMessage(content="Search"), AIMessage(content="Found"))
    state["current_turn_id"] = 9
    state["agent_results"] = {
        "9:plan_executor": {
            "agent_name": "plan_executor",
            "status": "success",
            "data": {},
            "failed_steps": [
                {
                    "step_index": 1,
                    "tool_name": "fetch_web_page_tool",
                    "error": "HTTP error 403",
                    "error_code": "FORBIDDEN",
                }
            ],
        }
    }

    outcome = infer_conversation_outcome(state)

    assert outcome == "partial_success"


def test_infer_conversation_outcome_reads_a_failed_dict_as_a_failure() -> None:
    """A totally failed plan is a failure, not « results exist, assume success »."""
    state = _state(
        HumanMessage(content="Read this"),
        AIMessage(content="I could not"),
        HumanMessage(content="ok"),
    )
    state["current_turn_id"] = 9
    state["agent_results"] = {
        "9:plan_executor": {
            "agent_name": "plan_executor",
            "status": "error",
            "data": None,
            "error": "HTTP error 403",
            "failed_steps": [
                {
                    "step_index": 0,
                    "tool_name": "fetch_web_page_tool",
                    "error": "HTTP error 403",
                    "error_code": "FORBIDDEN",
                }
            ],
        }
    }

    assert infer_conversation_outcome(state) == "failure"


def test_infer_conversation_outcome_results_with_data() -> None:
    """Test outcome inference when results have data (no explicit status)."""
    state = _state(HumanMessage(content="Search"))
    state["current_turn_id"] = 1
    state["agent_results"] = {"1:contacts_agent": {"data": {"contacts": []}}}

    outcome = infer_conversation_outcome(state)

    assert outcome == "success"  # Results with data → success


# ============================================================================
# TESTS - extract_agent_type()
# ============================================================================


def test_a_domain_named_by_a_result_is_never_the_label() -> None:
    """The graph writes results as dicts keyed by turn and agent: read there,
    the label named a shape nothing produces. (The state declares no
    ``agent_type`` at all: a key LangGraph would drop never reaches a reader.)"""
    state = _state()
    state["current_turn_id"] = 1
    state["agent_results"] = {"1:contacts_agent": {}}

    assert extract_agent_type(state) == "generic"
    state["execution_mode"] = "react"
    assert extract_agent_type(state) == "react"


def test_extract_agent_type_fallback() -> None:
    """Test agent type extraction fallback to 'generic'."""
    state = _state(HumanMessage(content="Hello"))

    agent_type = extract_agent_type(state)

    assert agent_type == "generic"  # Fallback


# ============================================================================
# TESTS - calculate_token_efficiency_ratio()
# ============================================================================


def test_calculate_token_efficiency_ratio_normal() -> None:
    """Test token efficiency ratio calculation."""
    ratio = calculate_token_efficiency_ratio(input_tokens=100, output_tokens=250)

    assert ratio == 2.5  # 250 / 100


def test_calculate_token_efficiency_ratio_zero_input() -> None:
    """Test token efficiency ratio with zero input tokens."""
    ratio = calculate_token_efficiency_ratio(input_tokens=0, output_tokens=100)

    assert ratio == 0.0  # Graceful handling


def test_calculate_token_efficiency_ratio_zero_output() -> None:
    """Test token efficiency ratio with zero output tokens."""
    ratio = calculate_token_efficiency_ratio(input_tokens=100, output_tokens=0)

    assert ratio == 0.0


def test_calculate_token_efficiency_ratio_high() -> None:
    """Test token efficiency ratio for verbose agent."""
    ratio = calculate_token_efficiency_ratio(input_tokens=100, output_tokens=500)

    assert ratio == 5.0  # High ratio (verbose)


def test_calculate_token_efficiency_ratio_low() -> None:
    """Test token efficiency ratio for concise agent."""
    ratio = calculate_token_efficiency_ratio(input_tokens=100, output_tokens=25)

    assert ratio == 0.25  # Low ratio (concise)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


def test_calculate_conversation_metrics_integration() -> None:
    """Integration test: Full conversation with all metrics."""
    state = _state(
        HumanMessage(content="Search Paul"),
        AIMessage(
            content="Found 3 contacts",
            usage_metadata={"input_tokens": 500, "output_tokens": 200, "total_tokens": 700},
            response_metadata={"model_name": "model-a"},
        ),
        HumanMessage(content="Show details"),
        AIMessage(
            content="Here are the details",
            usage_metadata={"input_tokens": 300, "output_tokens": 150, "total_tokens": 450},
            response_metadata={"model_name": "model-a"},
        ),
    )
    state["execution_mode"] = "pipeline"
    state["current_turn_id"] = 2
    state["agent_results"] = {"2:contacts_agent": {"status": "success", "data": {}}}

    with patch(f"{_BM}.quote_cached_cost_usd", side_effect=_tariff):
        metrics = calculate_conversation_metrics(state, config=None)

    # Assertions
    assert metrics.agent_type == "pipeline"
    assert metrics.tokens_total == 1150  # 500+200+300+150
    assert metrics.turns == 2  # 2 Human-AI pairs
    assert metrics.outcome == "success"
    assert metrics.message_count == 4
    # (500 + 2 x 200 + 300 + 2 x 150) tokens at one micro-dollar each.
    assert metrics.cost_usd == 0.0015


def test_a_state_with_an_empty_thread_yields_the_defaults() -> None:
    """No message, no execution mode, no agent: nothing to count or price."""
    metrics = calculate_conversation_metrics(_state(), config=None)

    assert metrics.agent_type == "generic"
    assert metrics.tokens_total == 0
    assert metrics.turns == 0
    assert metrics.cost_usd == 0.0
    assert metrics.outcome == OUTCOME_NO_AGENT  # no agent ran


def test_conversation_with_mixed_message_types() -> None:
    """Test conversation with SystemMessages and ToolMessages."""
    state = _state(
        SystemMessage(content="You are helpful"),
        HumanMessage(content="Search"),
        AIMessage(
            content="Searching...",
            usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        ),
        # ToolMessages would be here (not counted in turns)
    )

    metrics = calculate_conversation_metrics(state, config=None)

    assert metrics.turns == 1  # SystemMessage ignored
    assert metrics.tokens_total == 150
    assert metrics.message_count == 3


# ============================================================================
# TESTS - the state the graph really builds
# ============================================================================


def test_a_fresh_state_s_empty_planner_error_is_no_failure() -> None:
    """Every graph state carries ``planner_error`` — None on a fresh state.

    Its PRESENCE said nothing, and reading it counted every conversation as a
    failure since v1.0.0 (``agent_success_rate_total`` held only ``failure``).
    """
    state = create_initial_state(user_id=uuid4(), session_id="s", run_id="r")
    assert "planner_error" in state and state["planner_error"] is None
    state["current_turn_id"] = 1
    state["agent_results"] = {"1:contact_agent": {"status": "success", "data": {"n": 1}}}

    assert infer_conversation_outcome(state) == "success"
    metrics = calculate_conversation_metrics(state, config=None)
    assert metrics.outcome == "success"


def test_a_failed_planning_is_a_failure_on_the_real_shape() -> None:
    state = create_initial_state(user_id=uuid4(), session_id="s", run_id="r")
    state["planning_result"] = PlanningResult(plan=None, success=False, error="x")

    assert infer_conversation_outcome(state) == "failure"
    assert calculate_conversation_metrics(state, config=None).outcome == "failure"


def test_an_earlier_turn_s_agents_never_judge_a_later_turn() -> None:
    """``agent_results`` keeps every turn: a failed turn 1 must not make turn 2
    a partial success, nor turn 2's chat a failure."""
    state = create_initial_state(user_id=uuid4(), session_id="s", run_id="r")
    state["agent_results"] = {
        "1:email_agent": {"status": "error", "data": None},
        "2:contact_agent": {"status": "success", "data": {"n": 1}},
    }

    state["current_turn_id"] = 2
    assert infer_conversation_outcome(state) == "success"

    state["current_turn_id"] = 3  # a conversational turn after both
    assert infer_conversation_outcome(state) == OUTCOME_NO_AGENT


# ============================================================================
# TESTS - the turn's own evidence (review 7)
# ============================================================================


def _turn(
    *messages: BaseMessage,
    agent_results: dict[str, object] | None = None,
    current_turn_id: int = 0,
    react_agent_result: dict[str, object] | None = None,
) -> MessagesState:
    """A state whose last HumanMessage opens the current turn."""
    state = _state(HumanMessage(content="earlier"), *messages)
    state["current_turn_id"] = current_turn_id
    if agent_results is not None:
        state["agent_results"] = agent_results
    if react_agent_result is not None:
        state["react_agent_result"] = react_agent_result
    return state


def _tool(status: str, call_id: str = "c1") -> ToolMessage:
    return ToolMessage(content="x", tool_call_id=call_id, name="get_weather_tool", status=status)


_REACT_ANSWER: dict[str, object] = {"5:react_agent": {"data": {"react_synthesis": "answer"}}}


def test_a_react_turn_is_judged_on_its_tools_never_on_its_answer() -> None:
    """The answer is prose, merged status-less: read as data, a turn whose every
    call failed was a success by construction."""
    failed = _turn(
        HumanMessage(content="weather?"),
        _tool("error"),
        agent_results=_REACT_ANSWER,
        current_turn_id=5,
    )
    clean = _turn(
        HumanMessage(content="weather?"),
        _tool("success"),
        agent_results=_REACT_ANSWER,
        current_turn_id=5,
    )

    assert infer_conversation_outcome(failed) == "failure"
    assert infer_conversation_outcome(clean) == "success"


def test_a_react_turn_is_judged_on_its_result_never_call_by_call() -> None:
    """ADR-310: a failure the loop got past — its own call corrected, another
    source — fails nothing; what did not end complete is what the answer
    declares unresolved."""
    calls = (HumanMessage(content="weather?"), _tool("error"), _tool("success", "c2"))
    got_past = _turn(*calls, react_agent_result={"final_message": "Sunny."})
    declared = _turn(
        *calls, react_agent_result={"final_message": "Sunny.<unresolved>- the wind</unresolved>"}
    )

    assert infer_conversation_outcome(got_past) == "success"
    assert infer_conversation_outcome(declared) == "partial_success"


def test_a_gap_declared_when_every_call_came_back_did_not_end_complete() -> None:
    """A result that answers ANOTHER question is an obstacle like an error."""
    state = _turn(
        HumanMessage(content="tomorrow's weather?"),
        _tool("success"),
        react_agent_result={"final_message": "<unresolved>- tomorrow: served today</unresolved>"},
    )
    nothing_declared = _turn(
        HumanMessage(content="tomorrow's weather?"),
        _tool("success"),
        react_agent_result={"final_message": "Rain.<unresolved>none</unresolved>"},
    )

    assert infer_conversation_outcome(state) == "partial_success"
    assert infer_conversation_outcome(nothing_declared) == "success"


def test_a_call_the_loop_never_ran_is_no_verdict() -> None:
    """Declined by the person, or a repeat the loop guard blocked: a decision,
    never an execution — like a cancelled draft. Read as a ToolMessage with no
    error status, a turn whose only act was declined was a success."""
    declined = tool_call_not_run("declined", "c1", "send_email_tool")
    blocked = tool_call_not_run(repeated_call_message("block"), "c2", "get_weather_tool")
    decisions_only = _turn(HumanMessage(content="send it"), declined, blocked)
    with_a_read = _turn(HumanMessage(content="send it"), _tool("success", "c0"), declined)
    with_a_failure = _turn(HumanMessage(content="send it"), _tool("error", "c0"), declined)

    assert infer_conversation_outcome(decisions_only) == OUTCOME_NO_AGENT
    assert infer_conversation_outcome(with_a_read) == "success"
    assert infer_conversation_outcome(with_a_failure) == "failure"


def test_a_react_turn_that_called_no_tool_ran_no_agent() -> None:
    state = _turn(HumanMessage(content="hi"), agent_results=_REACT_ANSWER, current_turn_id=5)

    assert infer_conversation_outcome(state) == OUTCOME_NO_AGENT


def test_what_the_initiative_looked_up_of_its_own_accord_judges_nothing() -> None:
    """A lookup the initiative chose to make (ADR-062) never failed the
    person's request, which its failure used to demote to a partial success."""
    state = _state(HumanMessage(content="my agenda"))
    state["current_turn_id"] = 5
    state["agent_results"] = {
        "5:plan_executor": {"status": "success", "data": {"n": 1}},
        "5:initiative": {"status": "error", "data": None},
    }

    assert infer_conversation_outcome(state) == "success"


def test_an_earlier_turn_s_failed_tool_never_judges_this_one() -> None:
    state = _state(
        HumanMessage(content="read this page"),
        _tool("error"),
        AIMessage(content="I could not"),
        HumanMessage(content="thanks"),
    )

    assert infer_conversation_outcome(state) == OUTCOME_NO_AGENT


def test_a_loop_cut_by_its_budget_did_not_finish() -> None:
    state = _turn(
        HumanMessage(content="compare"),
        _tool("success"),
        react_agent_result={"final_message": "", "truncation": {"reason": "max_iterations"}},
    )

    assert infer_conversation_outcome(state) == "partial_success"


def test_the_confirmed_draft_judges_the_turn() -> None:
    """The act the person approved: a send that failed after confirmation is no
    success, even when the plan that prepared it succeeded."""
    base = _state(HumanMessage(content="send it"))
    base["current_turn_id"] = 5
    with_plan = base.copy()
    with_plan["agent_results"] = {"5:plan_executor": {"status": "success", "data": {}}}

    failed_send = {"status": "error", "action": "confirm"}
    sent = {"status": "success", "action": "confirm"}

    assert infer_conversation_outcome(with_plan, failed_send) == "partial_success"
    assert infer_conversation_outcome(base, failed_send) == "failure"
    assert infer_conversation_outcome(base, sent) == "success"


def _batch(*statuses: str) -> dict[str, object]:
    """A batch as the executor hands it to the response node."""
    entries = [{"status": status, "draft_id": f"d{i}"} for i, status in enumerate(statuses)]
    return DraftExecutionResult(
        success="error" not in statuses,
        draft_id="batch",
        draft_type="email",
        action="confirm_batch",
        result_data={"batch_results": entries, "success_count": statuses.count("success")},
    ).to_agent_result()


def test_a_batch_is_judged_entry_by_entry() -> None:
    """Its aggregate status says ``partial_error`` for a batch whose every entry
    failed, so read whole it was half a success. An entry the person cancelled
    executed nothing."""
    base = _state(HumanMessage(content="send them"))
    base["current_turn_id"] = 5

    assert _batch("error", "error")["status"] == "partial_error"
    assert infer_conversation_outcome(base, _batch("error", "error")) == "failure"
    assert infer_conversation_outcome(base, _batch("success", "error")) == "partial_success"
    assert infer_conversation_outcome(base, _batch("success", "cancelled")) == "success"
    assert infer_conversation_outcome(base, _batch("cancelled")) == OUTCOME_NO_AGENT


def test_a_draft_that_executed_nothing_is_no_verdict() -> None:
    """A cancellation, or an edit that asks again — the executor writes both as
    ``success``-looking results, and neither ran anything."""
    base = _state(HumanMessage(content="no"))
    base["current_turn_id"] = 5

    assert infer_conversation_outcome(base, {"status": "cancelled", "action": "cancel"}) == (
        OUTCOME_NO_AGENT
    )
    assert infer_conversation_outcome(base, {"status": "success", "action": "edit"}) == (
        OUTCOME_NO_AGENT
    )


def test_a_turn_whose_planner_produced_no_plan_is_a_failure() -> None:
    """The planner sends it to the response with no agent result: judged on the
    results alone, it passed for a conversational turn and was never counted.
    The checkpoint restores the dataclass (it is allowlisted); a mapping is
    read alike."""
    as_written = PlanningResult(plan=None, success=False, error="no plan")
    as_a_mapping = {"plan": None, "success": False}

    for planning_result in (as_written, as_a_mapping):
        state = _state(HumanMessage(content="do it"))
        state["planning_result"] = planning_result
        assert infer_conversation_outcome(state) == "failure"


def test_a_key_with_no_turn_judges_no_later_turn() -> None:
    """Composite keys exist since v1.0.0 and the cleanup reads a bare key as the
    OLDEST turn's: kept in every turn, one stale error failed every later chat."""
    state = _state(HumanMessage(content="thanks"))
    state["current_turn_id"] = 5
    state["agent_results"] = {"contacts_agent": {"status": "error"}}

    assert infer_conversation_outcome(state) == OUTCOME_NO_AGENT


def test_a_turn_id_is_matched_whole_never_as_a_prefix() -> None:
    state = _state(HumanMessage(content="hi"))
    state["current_turn_id"] = 1
    state["agent_results"] = {"11:plan_executor": {"status": "error"}}

    assert infer_conversation_outcome(state) == OUTCOME_NO_AGENT


def test_a_metrics_failure_judges_no_agent() -> None:
    """A calculation that broke is no agent failure: counted, it would be one."""
    with patch(
        "src.domains.agents.services.business_metrics.calculate_conversation_turns",
        side_effect=RuntimeError("boom"),
    ):
        metrics = calculate_conversation_metrics(_state())

    assert metrics.outcome == OUTCOME_NO_AGENT


def test_the_agent_label_is_the_turn_s_execution_mode() -> None:
    """The graph's results are dicts naming no domain: asked for an attribute,
    every series read « generic »."""
    state = _state()
    state["current_turn_id"] = 5
    state["agent_results"] = {
        "5:plan_executor": {"status": "success", "agent_name": "plan_executor"}
    }
    state["execution_mode"] = "react"

    assert extract_agent_type(state) == "react"
    assert extract_agent_type(_state()) == "generic"


def _session(
    exit_failure: BaseException | None,
) -> Callable[[], AbstractAsyncContextManager[Mock]]:
    """The ledger's own short session; ``exit_failure`` is what its commit raises."""

    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        yield Mock()
        if exit_failure is not None:
            raise exit_failure

    return _context


async def _run_cost(
    filed: object, pending_eur: float, *, exit_failure: BaseException | None = None
) -> float | None:
    """The cost of a run whose ledger row holds ``filed`` and whose tracker
    has ``pending_eur`` not filed yet, at 0.5 EUR per USD."""
    tracker = Mock(run_id="run-1")
    tracker.get_summary.return_value = {"cost_eur": pending_eur}
    repository = Mock()
    if isinstance(filed, BaseException):
        repository.get_token_summary_by_run_id = AsyncMock(side_effect=filed)
    else:
        repository.get_token_summary_by_run_id = AsyncMock(return_value=filed)
    token = current_tracker.set(tracker)
    try:
        with (
            patch(f"{_BM}.get_cached_usd_eur_rate", return_value=0.5),
            patch(f"{_BM}.ChatRepository", Mock(return_value=repository)),
            patch(f"{_BM}.get_db_context", _session(exit_failure)),
        ):
            return await current_turn_cost_usd()
    finally:
        current_tracker.reset(token)


async def test_a_turn_s_cost_is_its_run_s_ledger() -> None:
    """The thread's messages carry neither the router, the planner nor the
    agents: a successful turn used to record the thread's running total."""
    assert await _run_cost(None, 0.05) == 0.1


async def test_a_turn_resumed_after_a_question_counts_both_halves() -> None:
    """The run id is kept across the question and the first half was filed when
    it stopped: read from the tracker alone, the turn cost its second half."""
    first_half = Mock(total_cost_eur=Decimal("0.02"))

    assert await _run_cost(first_half, 0.03) == 0.1


class _DriverRefusal(Exception):
    """What a driver raises of its own: asyncpg refuses a connection with a
    class of its hierarchy (« too many clients already »), neither a
    ``SQLAlchemyError`` nor an ``OSError``."""


@pytest.mark.parametrize(
    "failure",
    [
        SQLAlchemyError("down"),
        TimeoutError("connect"),
        ConnectionRefusedError(),
        _DriverRefusal("sorry, too many clients already"),
    ],
)
async def test_a_ledger_that_cannot_be_read_is_no_cost(failure: BaseException) -> None:
    """A connection that cannot open raises a TimeoutError or an OSError, and a
    server that refuses it a class of the driver's own — neither a
    SQLAlchemyError: read on those alone, it reached the response node."""
    assert await _run_cost(failure, 0.03) is None


async def test_a_ledger_whose_commit_is_refused_is_no_cost() -> None:
    """The read succeeded and the commit at the session's exit did not (the
    connection dropped in between): on its own session, that refusal costs
    this figure alone."""
    refused = OperationalError("COMMIT", None, ConnectionResetError())

    assert await _run_cost(None, 0.03, exit_failure=refused) is None


@pytest.mark.parametrize("where", ["read", "exit"])
async def test_a_cancelled_ledger_read_stays_cancelled(where: str) -> None:
    """A metric's read never fails its turn — and never swallows its
    cancellation either: the turn stays cancelled."""
    cancelled = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        if where == "read":
            await _run_cost(cancelled, 0.03)
        else:
            await _run_cost(None, 0.03, exit_failure=cancelled)


async def test_no_run_ledger_is_no_cost() -> None:
    assert current_tracker.get() is None
    assert await current_turn_cost_usd() is None
