"""Integration tests for Prometheus /metrics endpoint.

Tests exposure of all instrumented metrics to ensure observability
dashboards have complete data.

Created: 2025-11-20
Phase: PHASE 1.2 - Metrics Instrumentation Validation
"""

import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_metrics_endpoint_accessible():
    """Test that /metrics endpoint is accessible and returns valid format."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")


def test_e2e_metric_exposed():
    """Test that e2e_request_duration_seconds metric is exposed.

    This metric tracks end-to-end request latency by intention and agent complexity.
    Critical for E2E performance dashboard.

    Note: Metrics are defined even if no values yet (TYPE/HELP comments present).
    """
    response = client.get("/metrics")
    assert "e2e_request_duration_seconds" in response.text

    # Verify metric is defined (at minimum TYPE declaration)
    assert (
        "# TYPE e2e_request_duration_seconds" in response.text
        or "e2e_request_duration_seconds_bucket" in response.text
    )


def test_hitl_metrics_exposed():
    """Test that HITL (Human-in-the-Loop) metrics are exposed.

    These metrics track user interaction patterns in conversational HITL:
    - Response time: How long users take to respond
    - Edit decisions: How often users modify agent suggestions
    - Rejections: Why users reject tool executions
    """
    response = client.get("/metrics")

    # Response time metric
    assert "hitl_user_response_time_seconds" in response.text

    # Edit decisions metric
    assert "hitl_edit_decisions_total" in response.text

    # Tool rejection metric
    assert "hitl_tool_rejections_by_reason_total" in response.text


def test_context_resolution_metrics_exposed():
    """Test that context resolution metrics are exposed.

    These metrics track multi-turn conversation context handling:
    - Attempts: Total resolution attempts by turn type
    - Confidence: Distribution of confidence scores
    - Turn type distribution: Breakdown of action/reference/conversational turns
    - Duration: Latency of context resolution

    Note: Metrics are defined even if no values yet (TYPE/HELP comments present).
    """
    response = client.get("/metrics")

    # Attempts counter
    assert "context_resolution_attempts_total" in response.text

    # Confidence histogram
    assert "context_resolution_confidence_score" in response.text

    # Turn type distribution counter
    assert "context_resolution_turn_type_distribution_total" in response.text

    # Duration histogram
    assert "context_resolution_duration_seconds" in response.text

    # Verify at least one metric has TYPE declaration
    assert (
        "# TYPE context_resolution_attempts_total" in response.text
        or "# TYPE context_resolution_confidence_score" in response.text
        or "# TYPE context_resolution_turn_type_distribution_total" in response.text
        or "# TYPE context_resolution_duration_seconds" in response.text
    )


def test_metrics_format_valid():
    """Test that metrics are in valid Prometheus format.

    Prometheus format requires:
    - TYPE comments defining metric type (counter, histogram, etc.)
    - HELP comments describing metrics
    - Metric lines with labels and values
    """
    response = client.get("/metrics")
    lines = response.text.split("\n")

    # Check for TYPE and HELP comments
    type_comments = [line for line in lines if line.startswith("# TYPE")]
    help_comments = [line for line in lines if line.startswith("# HELP")]

    assert len(type_comments) > 0, "No TYPE comments found in metrics output"
    assert len(help_comments) > 0, "No HELP comments found in metrics output"

    # Check for metric lines (not comments)
    metric_lines = [line for line in lines if line and not line.startswith("#")]
    assert len(metric_lines) > 0, "No metric data lines found"


def test_hitl_classification_metrics_exposed():
    """Test that HITL classification metrics are exposed.

    Phase 1.2 conversational HITL metrics:
    - Classification method (fast-path vs LLM)
    - Classification latency
    - Confidence scores
    - Clarification requests
    """
    response = client.get("/metrics")

    # Classification method counter
    assert "hitl_classification_method_total" in response.text

    # Classification duration histogram
    assert "hitl_classification_duration_seconds" in response.text

    # Confidence histogram
    assert "hitl_classification_confidence" in response.text

    # Clarification requests counter
    assert "hitl_clarification_requests_total" in response.text


def test_llm_cache_metrics_exposed():
    """Test that LLM cache metrics are exposed.

    LLM caching metrics for performance monitoring:
    - Cache hits/misses
    - Cache latency
    """
    response = client.get("/metrics")

    # Cache hit/miss metric
    assert "llm_cache" in response.text or "cache" in response.text.lower()


def test_metrics_no_sensitive_data():
    """Test that /metrics endpoint does not leak sensitive data.

    Ensure no API keys, tokens, or PII appears in metrics output.

    Note: The "@" pattern alone is too broad as it appears in legitimate contexts
    (like decorator syntax in Python tracebacks, test fixtures with email addresses).
    We look for more specific patterns that indicate actual sensitive data leakage.
    """
    import re

    response = client.get("/metrics")

    # Common sensitive patterns - more specific to avoid false positives
    sensitive_patterns = [
        r"sk-[a-zA-Z0-9]{20,}",  # OpenAI API keys (sk- followed by long alphanumeric)
        r"Bearer [a-zA-Z0-9_-]+",  # Auth tokens (Bearer followed by token)
        r"password\s*=",  # Password assignments
        r"secret\s*=",  # Secret assignments
    ]

    for pattern in sensitive_patterns:
        matches = re.findall(pattern, response.text, re.IGNORECASE)
        assert not matches, f"Sensitive pattern '{pattern}' found in metrics: {matches[:3]}..."

    # Also check for specific email patterns in metric labels (not in HELP text)
    # Emails in metric labels look like: label="user@example.com"
    email_in_label_pattern = r'="[^"]+@[^"]+\.[^"]+"'
    matches = re.findall(email_in_label_pattern, response.text)
    # Filter out known safe patterns (like example.com in HELP text)
    real_email_matches = [m for m in matches if "example.com" not in m and "test" not in m.lower()]
    assert (
        not real_email_matches
    ), f"Email addresses found in metric labels: {real_email_matches[:3]}..."


@pytest.mark.parametrize(
    "metric_name,metric_type",
    [
        ("e2e_request_duration_seconds", "histogram"),
        ("context_resolution_attempts_total", "counter"),
        ("hitl_user_response_time_seconds", "histogram"),
    ],
)
def test_specific_metrics_have_correct_type(metric_name: str, metric_type: str):
    """Test that specific metrics have correct Prometheus type declarations.

    Args:
        metric_name: Name of the metric to check
        metric_type: Expected Prometheus type (counter, histogram, gauge, summary)
    """
    response = client.get("/metrics")

    # Look for TYPE declaration
    type_declaration = f"# TYPE {metric_name} {metric_type}"
    assert (
        type_declaration in response.text
    ), f"Metric {metric_name} should be declared as {metric_type}"
