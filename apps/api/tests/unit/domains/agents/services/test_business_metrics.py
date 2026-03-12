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

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.domains.agents.services.business_metrics import (
    ConversationMetrics,
    calculate_agent_tool_approval_rate,
    calculate_conversation_metrics,
    calculate_conversation_turns,
    calculate_token_efficiency_ratio,
    calculate_total_cost_usd,
    calculate_total_tokens,
    extract_agent_type,
    infer_conversation_outcome,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_messages_with_tokens():
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
def sample_state_success():
    """Sample state for successful conversation."""
    return {
        "messages": [
            HumanMessage(content="Search contacts"),
            AIMessage(content="Found 5 contacts"),
        ],
        "agent_type": "contacts",
        "agent_results": [
            type(
                "AgentResult",
                (),
                {
                    "agent_type": "contacts",
                    "status": "success",
                    "data": {"contacts": []},
                },
            )()
        ],
    }


@pytest.fixture
def sample_state_failure():
    """Sample state for failed conversation."""
    return {
        "messages": [HumanMessage(content="Search contacts")],
        "agent_type": "contacts",
        "planner_error": {
            "message": "Validation failed",
            "errors": [],
        },
    }


# ============================================================================
# TESTS - calculate_conversation_metrics()
# ============================================================================


def test_calculate_conversation_metrics_success(sample_state_success):
    """Test conversation metrics calculation for successful conversation."""
    # Add usage_metadata to AIMessage
    sample_state_success["messages"][1].usage_metadata = {
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
    }

    metrics = calculate_conversation_metrics(sample_state_success, config=None)

    assert isinstance(metrics, ConversationMetrics)
    assert metrics.agent_type == "contacts"
    assert metrics.tokens_total == 150  # 100 + 50
    assert metrics.turns == 1  # 1 HumanMessage + 1 AIMessage
    assert metrics.outcome == "success"
    assert metrics.message_count == 2
    assert metrics.has_errors is False
    assert metrics.cost_usd > 0.0  # Fallback pricing applied


def test_calculate_conversation_metrics_failure(sample_state_failure):
    """Test conversation metrics calculation for failed conversation."""
    metrics = calculate_conversation_metrics(sample_state_failure, config=None)

    assert metrics.agent_type == "contacts"
    assert metrics.outcome == "failure"  # planner_error present
    assert metrics.has_errors is True
    assert metrics.message_count == 1


def test_calculate_conversation_metrics_abandoned():
    """Test conversation metrics calculation for abandoned conversation."""
    state = {
        "messages": [
            HumanMessage(content="Hi"),
            AIMessage(content="Hello"),
        ],
        # No agent_results, no planner_error → abandoned
    }

    metrics = calculate_conversation_metrics(state, config=None)

    assert metrics.outcome == "abandoned"
    assert metrics.has_errors is False


def test_calculate_conversation_metrics_graceful_degradation():
    """Test graceful degradation when state is malformed."""
    # Malformed state (missing required fields)
    state = {}  # Empty state

    metrics = calculate_conversation_metrics(state, config=None)

    # Should return defaults without crashing
    # Note: Empty state doesn't actually cause exception - extract_agent_type returns "generic"
    assert metrics.agent_type == "generic"  # Fallback from extract_agent_type
    assert metrics.outcome == "abandoned"  # No agent_results + 0 messages (<= 2) → abandoned
    assert metrics.tokens_total == 0
    assert metrics.cost_usd == 0.0
    assert metrics.has_errors is False  # No planner_error, outcome not failure/partial


# ============================================================================
# TESTS - calculate_total_tokens()
# ============================================================================


def test_calculate_total_tokens_with_usage_metadata(sample_messages_with_tokens):
    """Test token calculation with usage_metadata."""
    total = calculate_total_tokens(sample_messages_with_tokens)

    # 100 + 50 (first AIMessage) + 200 + 75 (second AIMessage) = 425
    assert total == 425


def test_calculate_total_tokens_empty_messages():
    """Test token calculation with empty messages list."""
    total = calculate_total_tokens([])

    assert total == 0


def test_calculate_total_tokens_no_ai_messages():
    """Test token calculation with no AIMessages."""
    messages = [
        HumanMessage(content="Hello"),
        SystemMessage(content="System prompt"),
    ]

    total = calculate_total_tokens(messages)

    assert total == 0  # No AIMessages with usage_metadata


def test_calculate_total_tokens_missing_usage_metadata():
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


def test_calculate_total_cost_usd_fallback_pricing(sample_messages_with_tokens):
    """Test cost calculation with fallback pricing."""
    cost = calculate_total_cost_usd(sample_messages_with_tokens)

    # Fallback pricing (gpt-4.1-mini rates):
    # Input: $0.15/1M, Output: $0.60/1M
    # Message 1: (100/1M * 0.15) + (50/1M * 0.60) = 0.000015 + 0.00003 = 0.000045
    # Message 2: (200/1M * 0.15) + (75/1M * 0.60) = 0.00003 + 0.000045 = 0.000075
    # Total: 0.00012
    expected_cost = 0.00012
    assert abs(cost - expected_cost) < 0.000001  # Precision tolerance


def test_calculate_total_cost_usd_zero_tokens():
    """Test cost calculation with zero tokens."""
    messages = [HumanMessage(content="Hello")]

    cost = calculate_total_cost_usd(messages)

    assert cost == 0.0


def test_calculate_total_cost_usd_precision():
    """Test cost calculation precision (6 decimals)."""
    messages = [
        AIMessage(
            content="Response",
            usage_metadata={
                "input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 2,
            },
        )
    ]

    cost = calculate_total_cost_usd(messages)

    # (1/1M * 0.15) + (1/1M * 0.60) = 0.00000075
    # Rounded to 6 decimals with round() → 0.000001 (rounds up from 0.00000075)
    assert cost == 0.000001  # 6-decimal precision with rounding


# ============================================================================
# TESTS - calculate_conversation_turns()
# ============================================================================


def test_calculate_conversation_turns_simple():
    """Test turn calculation with simple alternating messages."""
    state = {
        "messages": [
            HumanMessage(content="Hi"),
            AIMessage(content="Hello"),
            HumanMessage(content="How are you?"),
            AIMessage(content="Good"),
        ]
    }

    turns = calculate_conversation_turns(state)

    assert turns == 2  # 2 Human-AI pairs


def test_calculate_conversation_turns_consecutive_messages():
    """Test turn calculation with consecutive HumanMessages."""
    state = {
        "messages": [
            HumanMessage(content="Hi"),
            HumanMessage(content="Are you there?"),  # Consecutive
            AIMessage(content="Yes, hello!"),
        ]
    }

    turns = calculate_conversation_turns(state)

    assert turns == 1  # Consecutive HumanMessages = 1 turn


def test_calculate_conversation_turns_empty():
    """Test turn calculation with empty messages."""
    state = {"messages": []}

    turns = calculate_conversation_turns(state)

    assert turns == 0


def test_calculate_conversation_turns_only_human():
    """Test turn calculation with only HumanMessages."""
    state = {
        "messages": [
            HumanMessage(content="Hi"),
            HumanMessage(content="Hello?"),
        ]
    }

    turns = calculate_conversation_turns(state)

    assert turns == 0  # No AIMessage, no complete turn


def test_calculate_conversation_turns_system_messages():
    """Test turn calculation ignores SystemMessages."""
    state = {
        "messages": [
            SystemMessage(content="You are a helpful assistant"),
            HumanMessage(content="Hi"),
            AIMessage(content="Hello"),
        ]
    }

    turns = calculate_conversation_turns(state)

    assert turns == 1  # SystemMessage ignored


# ============================================================================
# TESTS - infer_conversation_outcome()
# ============================================================================


def test_infer_conversation_outcome_success():
    """Test outcome inference for successful conversation."""
    state = {
        "agent_results": [
            type("Result", (), {"status": "success", "data": {}})(),
        ],
        "messages": [HumanMessage(content="Search"), AIMessage(content="Found")],
    }

    outcome = infer_conversation_outcome(state)

    assert outcome == "success"


def test_infer_conversation_outcome_failure_planner_error():
    """Test outcome inference with planner_error."""
    state = {
        "planner_error": {"message": "Validation failed"},
        "messages": [HumanMessage(content="Search")],
    }

    outcome = infer_conversation_outcome(state)

    assert outcome == "failure"


def test_infer_conversation_outcome_failure_no_results():
    """Test outcome inference with no agent_results (long conversation)."""
    state = {
        "messages": [
            HumanMessage(content="Search"),
            AIMessage(content="Searching..."),
            HumanMessage(content="Any results?"),
            # No agent_results → failure
        ]
    }

    outcome = infer_conversation_outcome(state)

    assert outcome == "failure"  # Long conversation without results


def test_infer_conversation_outcome_abandoned_short():
    """Test outcome inference for abandoned short conversation."""
    state = {
        "messages": [
            HumanMessage(content="Hi"),
            # Very short, no results → abandoned
        ]
    }

    outcome = infer_conversation_outcome(state)

    assert outcome == "abandoned"


def test_infer_conversation_outcome_partial_success():
    """Test outcome inference for partial success (mixed results)."""
    state = {
        "agent_results": [
            type("Result", (), {"status": "success"})(),
            type("Result", (), {"status": "failure"})(),
        ],
        "messages": [HumanMessage(content="Search"), AIMessage(content="Found")],
    }

    outcome = infer_conversation_outcome(state)

    assert outcome == "partial_success"


def test_infer_conversation_outcome_results_with_data():
    """Test outcome inference when results have data (no explicit status)."""
    state = {
        "agent_results": [
            type("Result", (), {"data": {"contacts": []}})(),
        ],
        "messages": [HumanMessage(content="Search")],
    }

    outcome = infer_conversation_outcome(state)

    assert outcome == "success"  # Results with data → success


# ============================================================================
# TESTS - extract_agent_type()
# ============================================================================


def test_extract_agent_type_from_state():
    """Test agent type extraction from state field."""
    state = {"agent_type": "contacts"}

    agent_type = extract_agent_type(state)

    assert agent_type == "contacts"


def test_extract_agent_type_from_results():
    """Test agent type extraction from agent_results."""
    state = {
        "agent_results": [
            type("Result", (), {"agent_type": "emails"})(),
        ]
    }

    agent_type = extract_agent_type(state)

    assert agent_type == "emails"


def test_extract_agent_type_fallback():
    """Test agent type extraction fallback to 'generic'."""
    state = {
        "messages": [HumanMessage(content="Hello")],
        # No agent_type field, no agent_results
    }

    agent_type = extract_agent_type(state)

    assert agent_type == "generic"  # Fallback


def test_extract_agent_type_priority():
    """Test agent type extraction priority (state > results > fallback)."""
    state = {
        "agent_type": "contacts",  # Priority 1
        "agent_results": [
            type("Result", (), {"agent_type": "emails"})(),  # Priority 2 (ignored)
        ],
    }

    agent_type = extract_agent_type(state)

    assert agent_type == "contacts"  # State field takes priority


# ============================================================================
# TESTS - calculate_token_efficiency_ratio()
# ============================================================================


def test_calculate_token_efficiency_ratio_normal():
    """Test token efficiency ratio calculation."""
    ratio = calculate_token_efficiency_ratio(input_tokens=100, output_tokens=250)

    assert ratio == 2.5  # 250 / 100


def test_calculate_token_efficiency_ratio_zero_input():
    """Test token efficiency ratio with zero input tokens."""
    ratio = calculate_token_efficiency_ratio(input_tokens=0, output_tokens=100)

    assert ratio == 0.0  # Graceful handling


def test_calculate_token_efficiency_ratio_zero_output():
    """Test token efficiency ratio with zero output tokens."""
    ratio = calculate_token_efficiency_ratio(input_tokens=100, output_tokens=0)

    assert ratio == 0.0


def test_calculate_token_efficiency_ratio_high():
    """Test token efficiency ratio for verbose agent."""
    ratio = calculate_token_efficiency_ratio(input_tokens=100, output_tokens=500)

    assert ratio == 5.0  # High ratio (verbose)


def test_calculate_token_efficiency_ratio_low():
    """Test token efficiency ratio for concise agent."""
    ratio = calculate_token_efficiency_ratio(input_tokens=100, output_tokens=25)

    assert ratio == 0.25  # Low ratio (concise)


# ============================================================================
# TESTS - calculate_agent_tool_approval_rate() (Placeholder)
# ============================================================================


def test_calculate_agent_tool_approval_rate_placeholder():
    """Test tool approval rate calculation (placeholder implementation)."""
    state = {"messages": []}

    rate = calculate_agent_tool_approval_rate(state)

    # Placeholder returns 0.0
    assert rate == 0.0


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


def test_calculate_conversation_metrics_integration():
    """Integration test: Full conversation with all metrics."""
    state = {
        "messages": [
            HumanMessage(content="Search Paul"),
            AIMessage(
                content="Found 3 contacts",
                usage_metadata={
                    "input_tokens": 500,
                    "output_tokens": 200,
                    "total_tokens": 700,
                },
            ),
            HumanMessage(content="Show details"),
            AIMessage(
                content="Here are the details",
                usage_metadata={
                    "input_tokens": 300,
                    "output_tokens": 150,
                    "total_tokens": 450,
                },
            ),
        ],
        "agent_type": "contacts",
        "agent_results": [
            type("Result", (), {"status": "success", "data": {}})(),
        ],
    }

    metrics = calculate_conversation_metrics(state, config=None)

    # Assertions
    assert metrics.agent_type == "contacts"
    assert metrics.tokens_total == 1150  # 500+200+300+150
    assert metrics.turns == 2  # 2 Human-AI pairs
    assert metrics.outcome == "success"
    assert metrics.message_count == 4
    assert metrics.has_errors is False
    assert metrics.cost_usd > 0.0

    # Verify cost calculation (fallback pricing)
    expected_cost = (
        (500 / 1_000_000 * 0.15)
        + (200 / 1_000_000 * 0.60)
        + (300 / 1_000_000 * 0.15)
        + (150 / 1_000_000 * 0.60)
    )
    assert abs(metrics.cost_usd - expected_cost) < 0.000001


def test_calculate_conversation_metrics_edge_cases():
    """Integration test: Edge cases (empty state, missing fields)."""
    state = {
        "messages": [],
        # Missing agent_type, agent_results
    }

    metrics = calculate_conversation_metrics(state, config=None)

    # Graceful degradation - extract_agent_type returns "generic" fallback
    assert metrics.agent_type == "generic"  # Fallback from extract_agent_type
    assert metrics.tokens_total == 0
    assert metrics.turns == 0
    assert metrics.cost_usd == 0.0
    assert metrics.outcome == "abandoned"  # Empty messages (0 <= 2) + no agent_results → abandoned


def test_conversation_with_mixed_message_types():
    """Test conversation with SystemMessages and ToolMessages."""
    state = {
        "messages": [
            SystemMessage(content="You are helpful"),
            HumanMessage(content="Search"),
            AIMessage(
                content="Searching...",
                usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            ),
            # ToolMessages would be here (not counted in turns)
        ],
        "agent_type": "generic",
    }

    metrics = calculate_conversation_metrics(state, config=None)

    assert metrics.turns == 1  # SystemMessage ignored
    assert metrics.tokens_total == 150
    assert metrics.message_count == 3
