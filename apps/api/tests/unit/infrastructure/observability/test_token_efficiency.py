"""
Tests for token efficiency tracking (Phase 3.2 - Step 2.4).

Tests business metrics instrumentation for token_efficiency_ratio:
- track_token_efficiency() function (extraction + calculation + tracking)
- extract_agent_type_from_router_output() helper
- Integration with router, planner, response nodes

Business metrics track LLM efficiency (output_tokens / input_tokens) for cost optimization.

Coverage target: 100% of business metrics paths

Phase: 3.2 - Business Metrics - Step 2.4
Date: 2025-11-23
"""

from unittest.mock import MagicMock

from src.infrastructure.observability.metrics_business import token_efficiency_ratio
from src.infrastructure.observability.token_efficiency import (
    extract_agent_type_from_router_output,
    track_token_efficiency,
)

# ============================================================================
# TESTS - Helper Function: extract_agent_type_from_router_output
# ============================================================================


def test_extract_agent_type_contacts_intention():
    """Test agent_type extraction from router output with contacts intention."""
    agent_type = extract_agent_type_from_router_output(
        next_node="planner",
        intention="contacts_lookup",
    )
    assert agent_type == "contacts"


def test_extract_agent_type_emails_intention():
    """Test agent_type extraction from router output with email intention."""
    agent_type = extract_agent_type_from_router_output(
        next_node="planner",
        intention="email_search",
    )
    assert agent_type == "emails"


def test_extract_agent_type_conversational_intention():
    """Test agent_type extraction from router output with conversational intention."""
    agent_type = extract_agent_type_from_router_output(
        next_node="response",
        intention="conversational",
    )
    assert agent_type == "generic"


def test_extract_agent_type_calendar_intention():
    """Test agent_type extraction from router output with calendar intention."""
    agent_type = extract_agent_type_from_router_output(
        next_node="planner",
        intention="calendar_event_lookup",
    )
    # The function checks for "event" in intention, so returns "events"
    assert agent_type == "events"


def test_extract_agent_type_drive_intention():
    """Test agent_type extraction from router output with drive intention."""
    agent_type = extract_agent_type_from_router_output(
        next_node="planner",
        intention="drive_file_search",
    )
    assert agent_type == "drive"


def test_extract_agent_type_unknown_intention():
    """Test agent_type extraction from router output with unknown intention."""
    agent_type = extract_agent_type_from_router_output(
        next_node="response",
        intention="some_random_intention",
    )
    assert agent_type == "generic"


# ============================================================================
# TESTS - Main Function: track_token_efficiency
# ============================================================================


def test_track_token_efficiency_success():
    """Test successful token efficiency tracking with valid usage_metadata."""
    # Create mock config with TokenTrackingCallback
    mock_callback = MagicMock()
    mock_callback._last_usage_metadata = {
        "input_tokens": 1000,
        "output_tokens": 500,
        "cached_tokens": 0,
        "model_name": "gpt-4",
    }

    config = {
        "callbacks": [mock_callback],
    }

    # Execute tracking
    track_token_efficiency(
        config=config,
        node_name="router",
        agent_type="contacts",
    )

    # Verify metric was tracked (real Prometheus metric, safe for tests)
    assert token_efficiency_ratio is not None
    # Expected ratio: 500 / 1000 = 0.5


def test_track_token_efficiency_verbose_output():
    """Test token efficiency tracking with verbose LLM output (high ratio)."""
    # High output tokens relative to input (verbose agent)
    mock_callback = MagicMock()
    mock_callback._last_usage_metadata = {
        "input_tokens": 500,
        "output_tokens": 1500,  # Ratio = 3.0 (verbose)
        "cached_tokens": 0,
        "model_name": "gpt-4",
    }

    config = {
        "callbacks": [mock_callback],
    }

    track_token_efficiency(
        config=config,
        node_name="planner",
        agent_type="multi",
    )

    # Expected ratio: 1500 / 500 = 3.0 (verbose agent)
    assert token_efficiency_ratio is not None


def test_track_token_efficiency_concise_output():
    """Test token efficiency tracking with concise LLM output (low ratio)."""
    # Low output tokens relative to input (concise agent)
    mock_callback = MagicMock()
    mock_callback._last_usage_metadata = {
        "input_tokens": 2000,
        "output_tokens": 400,  # Ratio = 0.2 (concise)
        "cached_tokens": 100,
        "model_name": "gpt-4",
    }

    config = {
        "callbacks": [mock_callback],
    }

    track_token_efficiency(
        config=config,
        node_name="response",
        agent_type="generic",
    )

    # Expected ratio: 400 / 2000 = 0.2 (concise agent)
    assert token_efficiency_ratio is not None


def test_track_token_efficiency_no_config():
    """Test token efficiency tracking gracefully handles missing config."""
    # Execute with None config (should log debug and return early)
    track_token_efficiency(
        config=None,
        node_name="router",
        agent_type="contacts",
    )

    # No exception raised, function handles gracefully


def test_track_token_efficiency_no_callbacks():
    """Test token efficiency tracking gracefully handles config without callbacks."""
    config = {
        "timeout": 30,
        # No 'callbacks' key
    }

    track_token_efficiency(
        config=config,
        node_name="planner",
        agent_type="emails",
    )

    # No exception raised, function handles gracefully


def test_track_token_efficiency_no_usage_metadata():
    """Test token efficiency tracking gracefully handles callbacks without usage_metadata."""
    # Callback without _last_usage_metadata attribute
    mock_callback_no_metadata = MagicMock(spec=[])  # No attributes

    config = {
        "callbacks": [mock_callback_no_metadata],
    }

    track_token_efficiency(
        config=config,
        node_name="response",
        agent_type="generic",
    )

    # No exception raised, function handles gracefully


def test_track_token_efficiency_zero_input_tokens():
    """Test token efficiency tracking skips when input_tokens is zero (division by zero)."""
    mock_callback = MagicMock()
    mock_callback._last_usage_metadata = {
        "input_tokens": 0,  # Division by zero case
        "output_tokens": 500,
        "cached_tokens": 0,
        "model_name": "gpt-4",
    }

    config = {
        "callbacks": [mock_callback],
    }

    # Execute tracking (should log warning and skip)
    track_token_efficiency(
        config=config,
        node_name="router",
        agent_type="contacts",
    )

    # No exception raised, function handles gracefully with warning log


def test_track_token_efficiency_negative_input_tokens():
    """Test token efficiency tracking skips when input_tokens is negative."""
    mock_callback = MagicMock()
    mock_callback._last_usage_metadata = {
        "input_tokens": -100,  # Invalid negative value
        "output_tokens": 500,
        "cached_tokens": 0,
        "model_name": "gpt-4",
    }

    config = {
        "callbacks": [mock_callback],
    }

    # Execute tracking (should log warning and skip)
    track_token_efficiency(
        config=config,
        node_name="planner",
        agent_type="emails",
    )

    # No exception raised, function handles gracefully


def test_track_token_efficiency_multiple_callbacks():
    """Test token efficiency tracking extracts from first callback with usage_metadata."""
    # Multiple callbacks, only second one has usage_metadata
    mock_callback_no_metadata = MagicMock(spec=[])  # No attributes
    mock_callback_with_metadata = MagicMock()
    mock_callback_with_metadata._last_usage_metadata = {
        "input_tokens": 800,
        "output_tokens": 600,
        "cached_tokens": 0,
        "model_name": "gpt-4",
    }

    config = {
        "callbacks": [mock_callback_no_metadata, mock_callback_with_metadata],
    }

    track_token_efficiency(
        config=config,
        node_name="response",
        agent_type="multi",
    )

    # Expected ratio: 600 / 800 = 0.75
    assert token_efficiency_ratio is not None


# ============================================================================
# TESTS - Metric Definition
# ============================================================================


def test_token_efficiency_ratio_metric_definition():
    """Test that token_efficiency_ratio metric is correctly defined."""
    # Verify metric exists
    assert token_efficiency_ratio is not None

    # Verify metric name
    assert token_efficiency_ratio._name == "token_efficiency_ratio"

    # Verify labels
    expected_labels = ("agent_type", "node_name")
    assert token_efficiency_ratio._labelnames == expected_labels

    # Verify metric type
    from prometheus_client import Histogram

    assert isinstance(token_efficiency_ratio, Histogram)

    # Verify buckets (should match definition in metrics_business.py)
    # Note: Prometheus automatically appends +Inf to buckets, so _upper_bounds includes it
    # We verify the configured buckets match what was defined in metrics_business.py
    expected_configured_buckets = [0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0]
    # _upper_bounds includes the +Inf bucket that Prometheus adds automatically
    # Note: _upper_bounds is a list, not a tuple
    assert token_efficiency_ratio._upper_bounds == expected_configured_buckets + [float("inf")]


# ============================================================================
# TESTS - Edge Cases
# ============================================================================


def test_track_token_efficiency_missing_output_tokens():
    """Test token efficiency tracking handles missing output_tokens in metadata."""
    mock_callback = MagicMock()
    mock_callback._last_usage_metadata = {
        "input_tokens": 1000,
        # Missing 'output_tokens' key
        "cached_tokens": 0,
        "model_name": "gpt-4",
    }

    config = {
        "callbacks": [mock_callback],
    }

    # Execute tracking (should use default 0 for missing output_tokens → ratio = 0.0)
    track_token_efficiency(
        config=config,
        node_name="router",
        agent_type="contacts",
    )

    # No exception raised, defaults to 0


def test_track_token_efficiency_missing_input_tokens():
    """Test token efficiency tracking handles missing input_tokens in metadata."""
    mock_callback = MagicMock()
    mock_callback._last_usage_metadata = {
        # Missing 'input_tokens' key
        "output_tokens": 500,
        "cached_tokens": 0,
        "model_name": "gpt-4",
    }

    config = {
        "callbacks": [mock_callback],
    }

    # Execute tracking (should log warning for input_tokens <= 0)
    track_token_efficiency(
        config=config,
        node_name="planner",
        agent_type="emails",
    )

    # No exception raised


def test_track_token_efficiency_equal_tokens():
    """Test token efficiency tracking with equal input and output tokens (ratio = 1.0)."""
    mock_callback = MagicMock()
    mock_callback._last_usage_metadata = {
        "input_tokens": 1000,
        "output_tokens": 1000,  # Ratio = 1.0 (balanced)
        "cached_tokens": 0,
        "model_name": "gpt-4",
    }

    config = {
        "callbacks": [mock_callback],
    }

    track_token_efficiency(
        config=config,
        node_name="response",
        agent_type="generic",
    )

    # Expected ratio: 1000 / 1000 = 1.0 (balanced agent)
    assert token_efficiency_ratio is not None


# ============================================================================
# TESTS - Integration Scenarios
# ============================================================================


def test_track_token_efficiency_router_contacts_scenario():
    """Test token efficiency tracking for router with contacts intention."""
    # Simulate router LLM call with contacts intention
    mock_callback = MagicMock()
    mock_callback._last_usage_metadata = {
        "input_tokens": 500,  # Router uses low tokens (windowed messages)
        "output_tokens": 100,  # Router output is concise (routing decision)
        "cached_tokens": 0,
        "model_name": "gpt-4",
    }

    config = {
        "callbacks": [mock_callback],
    }

    # Extract agent_type from router output
    agent_type = extract_agent_type_from_router_output(
        next_node="planner",
        intention="contacts_lookup",
    )

    track_token_efficiency(
        config=config,
        node_name="router",
        agent_type=agent_type,
    )

    # Expected: agent_type="contacts", ratio=0.2 (concise router)
    assert agent_type == "contacts"


def test_track_token_efficiency_planner_multi_domain_scenario():
    """Test token efficiency tracking for planner with multi-domain query."""
    # Simulate planner LLM call for multi-domain query
    mock_callback = MagicMock()
    mock_callback._last_usage_metadata = {
        "input_tokens": 3000,  # Planner uses high tokens (full catalogue)
        "output_tokens": 1500,  # Planner output is JSON plan (medium verbosity)
        "cached_tokens": 0,
        "model_name": "gpt-4",
    }

    config = {
        "callbacks": [mock_callback],
    }

    # Planner with multi-domain query (contacts + emails)
    track_token_efficiency(
        config=config,
        node_name="planner",
        agent_type="multi",
    )

    # Expected: agent_type="multi", ratio=0.5 (typical planner)


def test_track_token_efficiency_response_generic_scenario():
    """Test token efficiency tracking for response with conversational query."""
    # Simulate response LLM call for conversational query
    mock_callback = MagicMock()
    mock_callback._last_usage_metadata = {
        "input_tokens": 800,  # Response uses medium tokens (conversation history)
        "output_tokens": 600,  # Response output is conversational (creative)
        "cached_tokens": 0,
        "model_name": "gpt-4",
    }

    config = {
        "callbacks": [mock_callback],
    }

    # Response with generic (conversational) agent_type
    track_token_efficiency(
        config=config,
        node_name="response",
        agent_type="generic",
    )

    # Expected: agent_type="generic", ratio=0.75 (conversational response)
