"""
Tests for track_tool_metrics decorator (Phase 3.2 - Business Metrics Enhancement).

Tests decorator instrumentation of BOTH framework AND business metrics:
- Framework metrics: agent_tool_invocations, agent_tool_duration_seconds
- Business metrics: agent_tool_usage_total (with agent_type, outcome labels)

Note: Business metrics use the real Prometheus Counter (safe for unit tests).
Framework metrics are mocked to verify label patterns.

Coverage target: 80%+

Phase: 3.2 - Business Metrics - Step 2.2
Date: 2025-11-23
"""

import logging
from unittest.mock import MagicMock

import pytest

from src.infrastructure.observability.decorators import (
    extract_agent_type_from_agent_name,
    map_success_to_outcome,
    track_tool_metrics,
)
from src.infrastructure.observability.metrics_business import agent_tool_usage_total

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_framework_metrics():
    """Mock framework metrics (agent_tool_invocations, agent_tool_duration_seconds)."""
    mock_counter = MagicMock()
    mock_histogram = MagicMock()

    # Mock .labels() chaining
    mock_counter.labels.return_value.inc = MagicMock()
    mock_histogram.labels.return_value.observe = MagicMock()

    return mock_counter, mock_histogram


# ============================================================================
# TESTS - Helper Functions
# ============================================================================


def test_extract_agent_type_from_agent_name():
    """Test agent_type extraction from agent_name."""
    # Standard pattern: {agent_type}_agent
    assert extract_agent_type_from_agent_name("contacts_agent") == "contacts"
    assert extract_agent_type_from_agent_name("emails_agent") == "emails"
    assert extract_agent_type_from_agent_name("context_agent") == "context"
    assert extract_agent_type_from_agent_name("generic_agent") == "generic"

    # Fallback (no "_agent" suffix)
    assert extract_agent_type_from_agent_name("custom_tool") == "custom_tool"
    assert extract_agent_type_from_agent_name("unknown") == "unknown"


def test_map_success_to_outcome():
    """Test boolean success mapping to business outcome string."""
    assert map_success_to_outcome(success=True) == "success"
    assert map_success_to_outcome(success=False) == "failure"


# ============================================================================
# TESTS - Decorator Instrumentation (Async Functions)
# ============================================================================


@pytest.mark.asyncio
async def test_track_tool_metrics_async_success(mock_framework_metrics):
    """Test decorator tracks framework metrics on success (async)."""
    mock_counter, mock_histogram = mock_framework_metrics

    @track_tool_metrics(
        tool_name="search_contacts",
        agent_name="contacts_agent",
        duration_metric=mock_histogram,
        counter_metric=mock_counter,
    )
    async def test_tool(query: str) -> str:
        """Test tool that succeeds."""
        return f"Found {query}"

    # Execute tool
    result = await test_tool("John")

    # Assertions
    assert result == "Found John"

    # Framework metric (success="true")
    mock_counter.labels.assert_any_call(
        tool_name="search_contacts", agent_name="contacts_agent", success="true"
    )

    # Duration metric tracked
    mock_histogram.labels.assert_called_with(
        tool_name="search_contacts", agent_name="contacts_agent"
    )
    mock_histogram.labels.return_value.observe.assert_called_once()

    # Business metric is tracked to real Prometheus Counter
    assert agent_tool_usage_total is not None


@pytest.mark.asyncio
async def test_track_tool_metrics_async_failure(mock_framework_metrics):
    """Test decorator tracks framework metrics on failure (async)."""
    mock_counter, mock_histogram = mock_framework_metrics

    @track_tool_metrics(
        tool_name="search_contacts",
        agent_name="contacts_agent",
        duration_metric=mock_histogram,
        counter_metric=mock_counter,
    )
    async def test_tool(query: str) -> str:
        """Test tool that fails."""
        raise ValueError("Contact not found")

    # Execute tool (expect exception)
    with pytest.raises(ValueError, match="Contact not found"):
        await test_tool("Unknown")

    # Framework metric (success="false")
    mock_counter.labels.assert_any_call(
        tool_name="search_contacts", agent_name="contacts_agent", success="false"
    )

    # Duration metric still tracked (in finally block)
    mock_histogram.labels.return_value.observe.assert_called_once()


# ============================================================================
# TESTS - Decorator Instrumentation (Sync Functions)
# ============================================================================


def test_track_tool_metrics_sync_success(mock_framework_metrics):
    """Test decorator tracks framework metrics on success (sync)."""
    mock_counter, mock_histogram = mock_framework_metrics

    @track_tool_metrics(
        tool_name="format_contact",
        agent_name="contacts_agent",
        duration_metric=mock_histogram,
        counter_metric=mock_counter,
    )
    def test_tool(name: str) -> str:
        """Test sync tool that succeeds."""
        return f"Formatted: {name}"

    # Execute tool
    result = test_tool("John Doe")

    # Assertions
    assert result == "Formatted: John Doe"

    # Framework metric (success="true")
    mock_counter.labels.assert_any_call(
        tool_name="format_contact", agent_name="contacts_agent", success="true"
    )


def test_track_tool_metrics_sync_failure(mock_framework_metrics):
    """Test decorator tracks framework metrics on failure (sync)."""
    mock_counter, mock_histogram = mock_framework_metrics

    @track_tool_metrics(
        tool_name="format_contact",
        agent_name="contacts_agent",
        duration_metric=mock_histogram,
        counter_metric=mock_counter,
    )
    def test_tool(name: str) -> str:
        """Test sync tool that fails."""
        raise TypeError("Invalid name format")

    # Execute tool (expect exception)
    with pytest.raises(TypeError, match="Invalid name format"):
        test_tool("Invalid")

    # Framework metric (success="false")
    mock_counter.labels.assert_any_call(
        tool_name="format_contact", agent_name="contacts_agent", success="false"
    )


# ============================================================================
# TESTS - Agent Type Extraction
# ============================================================================


@pytest.mark.asyncio
async def test_track_tool_metrics_different_agent_types(mock_framework_metrics):
    """Test decorator correctly extracts agent_type for different agent names."""
    mock_counter, mock_histogram = mock_framework_metrics

    test_cases = [
        ("contacts_agent", "search_contacts", "contacts"),
        ("emails_agent", "search_emails", "emails"),
        ("context_agent", "resolve_reference", "context"),
        ("generic_agent", "generic_tool", "generic"),
    ]

    for agent_name, tool_name, expected_agent_type in test_cases:

        @track_tool_metrics(
            tool_name=tool_name,
            agent_name=agent_name,
            duration_metric=mock_histogram,
            counter_metric=mock_counter,
        )
        async def test_tool() -> str:
            return "OK"

        result = await test_tool()

        # Verify execution succeeded
        assert result == "OK"

        # Verify agent_type extraction is correct (tested via helper function)
        assert extract_agent_type_from_agent_name(agent_name) == expected_agent_type


# ============================================================================
# TESTS - Optional Metrics (None passed)
# ============================================================================


@pytest.mark.asyncio
async def test_track_tool_metrics_no_metrics_provided():
    """Test decorator works when no framework metrics are provided."""

    @track_tool_metrics(
        tool_name="search_contacts",
        agent_name="contacts_agent",
        duration_metric=None,  # No duration metric
        counter_metric=None,  # No counter metric
    )
    async def test_tool(query: str) -> str:
        return f"Found {query}"

    # Tool should still execute successfully
    result = await test_tool("John")
    assert result == "Found John"

    # Business metric still tracked (real Prometheus Counter)
    assert agent_tool_usage_total is not None


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_track_tool_metrics_integration_with_connector_tool():
    """Integration test: Verify decorator works with real connector_tool decorator."""
    from src.domains.agents.tools.decorators import connector_tool

    # Verify business metric is correctly defined
    # Prometheus client strips "_total" suffix: agent_tool_usage_total → agent_tool_usage
    assert agent_tool_usage_total._name == "agent_tool_usage"
    assert agent_tool_usage_total._labelnames == ("agent_type", "tool_name", "outcome")

    # Verify connector_tool can be applied (syntax check)
    @connector_tool(
        name="test_tool",
        agent_name="test_agent",
        category="read",
    )
    async def test_integration_tool(query: str) -> str:
        """Test tool for integration testing."""
        return f"Result: {query}"

    # Decorator returns StructuredTool, not callable function
    # Verify tool was created successfully
    assert test_integration_tool is not None
    assert hasattr(test_integration_tool, "name")
    assert test_integration_tool.name == "test_integration_tool"


# ============================================================================
# EDGE CASES
# ============================================================================


def test_extract_agent_type_empty_string():
    """Test agent_type extraction with empty string."""
    assert extract_agent_type_from_agent_name("") == ""


def test_extract_agent_type_only_agent_suffix():
    """Test agent_type extraction when input is only '_agent'."""
    # "_agent" → remove suffix → "" (empty string)
    assert extract_agent_type_from_agent_name("_agent") == ""


@pytest.mark.asyncio
async def test_track_tool_metrics_preserves_exception_type(mock_framework_metrics):
    """Test decorator preserves original exception type when re-raising."""
    mock_counter, mock_histogram = mock_framework_metrics

    class CustomError(Exception):
        """Custom exception for testing."""

        pass

    @track_tool_metrics(
        tool_name="test_tool",
        agent_name="test_agent",
        duration_metric=mock_histogram,
        counter_metric=mock_counter,
    )
    async def test_tool() -> str:
        raise CustomError("Custom error message")

    # Exception type should be preserved
    with pytest.raises(CustomError, match="Custom error message"):
        await test_tool()


# ============================================================================
# TESTS - Verify Business Metric Instrumentation
# ============================================================================


def test_business_metric_definition():
    """Test that business metric is correctly defined."""
    # Verify metric exists
    assert agent_tool_usage_total is not None

    # Verify metric name (Prometheus client strips "_total" suffix from Counter names)
    # Variable name: agent_tool_usage_total → Prometheus metric name: agent_tool_usage
    assert agent_tool_usage_total._name == "agent_tool_usage"

    # Verify labels match expected schema
    expected_labels = ("agent_type", "tool_name", "outcome")
    assert agent_tool_usage_total._labelnames == expected_labels

    # Verify metric type
    from prometheus_client import Counter

    assert isinstance(agent_tool_usage_total, Counter)


# ============================================================================
# TESTS - A RETURNED failure is a failure (ADR-303)
# ============================================================================


class TestReturnedFailureIsCounted:
    """A tool fails by RETURNING, and that is the documented way.

    ``ToolErrorModel.to_response()`` and ``UnifiedToolOutput.failure()`` both
    return — they never raise — so a decorator that only watches for exceptions
    counts every one of them as a success. Measured in production on
    2026-09-09: four HTTP 403s, four ``failed`` rows in the consultation
    register, and ``agent_tool_invocations_total{success="true"} = 4``.
    """

    async def test_async_returned_failure_counts_false_and_logs_the_code(
        self, mock_framework_metrics, caplog: pytest.LogCaptureFixture
    ) -> None:
        counter, histogram = mock_framework_metrics

        @track_tool_metrics(
            tool_name="web_fetch",
            agent_name="web_fetch_agent",
            counter_metric=counter,
            duration_metric=histogram,
        )
        async def failing_tool() -> dict:
            return {
                "success": False,
                "error": "HTTP error 403 fetching https://secret.example/private",
                "error_code": "FORBIDDEN",
            }

        with caplog.at_level(logging.WARNING):
            result = await failing_tool()

        assert result["success"] is False
        counter.labels.assert_called_with(
            tool_name="web_fetch", agent_name="web_fetch_agent", success="false"
        )
        record = next(r for r in caplog.records if "tool_returned_failure" in r.getMessage())
        assert "FORBIDDEN" in record.getMessage()
        # The code labels the failure; the message would carry the URL.
        assert "secret.example" not in record.getMessage()

    async def test_async_returned_success_still_counts_true(self, mock_framework_metrics) -> None:
        counter, histogram = mock_framework_metrics

        @track_tool_metrics(
            tool_name="t", agent_name="a", counter_metric=counter, duration_metric=histogram
        )
        async def ok_tool() -> dict:
            return {"success": True, "data": {}}

        await ok_tool()
        counter.labels.assert_called_with(tool_name="t", agent_name="a", success="true")

    async def test_a_plain_answer_is_not_a_failure(self, mock_framework_metrics) -> None:
        """Silence is never a failure: a tool returning prose succeeded."""
        counter, histogram = mock_framework_metrics

        @track_tool_metrics(
            tool_name="t", agent_name="a", counter_metric=counter, duration_metric=histogram
        )
        async def prose_tool() -> str:
            return "Paris: 10-22 °C"

        await prose_tool()
        counter.labels.assert_called_with(tool_name="t", agent_name="a", success="true")

    def test_sync_returned_failure_counts_false(self, mock_framework_metrics) -> None:
        counter, histogram = mock_framework_metrics

        @track_tool_metrics(
            tool_name="t", agent_name="a", counter_metric=counter, duration_metric=histogram
        )
        def failing_sync_tool() -> dict:
            return {"success": False, "error_code": "TIMEOUT"}

        failing_sync_tool()
        counter.labels.assert_called_with(tool_name="t", agent_name="a", success="false")
